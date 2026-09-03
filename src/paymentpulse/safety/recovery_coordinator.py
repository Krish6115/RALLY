"""
Recovery Coordinator — End-to-End Orchestrator with Safety Invariants.

Enforces:
1. Concurrency locking per payment_id (exactly one worker proceeds).
2. Hard constraint pre-filtering (merchant policy, opt-out, attempt caps).
3. Live payment state verification immediately prior to dispatch (Governing Invariant).
4. Idempotent action dispatch.
5. Timeout / UNKNOWN state handling and explicit reconciliation.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Optional

from paymentpulse.domain.entities import (
    RecoveryAction,
    RecoveryExecution,
    PaymentStatus,
)
from paymentpulse.safety.state_machine import (
    PaymentStateMachine,
    PaymentLifecycleState,
    RecoveryLifecycleState,
    InvalidStateTransitionError,
)
from paymentpulse.safety.idempotency import IdempotencyStore
from paymentpulse.policy.engine import DecisionPipeline
from paymentpulse.policy.constraints import PolicyConstraints
from paymentpulse.execution.adapter import ExecutionAdapter

logger = logging.getLogger(__name__)


class RecoveryCoordinator:
    """
    Coordinates decisioning and safe execution.
    """

    def __init__(
        self,
        policy: DecisionPipeline,
        action_executor: ExecutionAdapter,
        idempotency_store: IdempotencyStore,
    ):
        self.pipeline = policy
        self.executor = action_executor
        self.idempotency_store = idempotency_store

    def handle_payment_failure(
        self,
        event_id: str,
        payment_id: str,
        order_id: str,
        amount_inr: float,
        model_version: str,
        feature_snapshot_id: str,
        uplift_estimates: dict[str, float],
        constraints: PolicyConstraints,
        state_machine: PaymentStateMachine,
        live_state_fetcher: Callable[[str], str],
        feature_staleness_seconds: float = 0.0,
    ) -> tuple[bool, Optional[RecoveryExecution], str, Optional[PolicyDecision]]:
        """
        Processes a payment failure event end-to-end under strict concurrency & safety invariants.

        Returns:
            (committed, execution_record_or_none, message, decision_or_none)
        """
        # Step 1: Concurrency Lock per payment
        # Exactly one worker can process recovery for this payment at a time!
        acquired = self.idempotency_store.acquire_lock(payment_id)
        if not acquired:
            logger.warning(
                f"[CONCURRENCY] Worker rejected for payment {payment_id} — lock already held."
            )
            return False, None, "CONCURRENT_LOCK_HELD", None

        try:
            # Step 2: Canonical State Verification
            if state_machine.payment_state.is_terminal_success:
                logger.info(
                    f"[STATE] Payment {payment_id} is already in terminal state {state_machine.payment_state.value}. Aborting."
                )
                state_machine.force_terminate("payment_already_captured")
                return False, None, "PAYMENT_ALREADY_SUCCEEDED", None

            if state_machine.recovery_state.is_terminal:
                logger.info(
                    f"[STATE] Recovery for payment {payment_id} is already terminal ({state_machine.recovery_state.value}). Aborting."
                )
                return False, None, "RECOVERY_ALREADY_TERMINAL", None

            # Check if an action is already executing or unknown
            if state_machine.recovery_state in (
                RecoveryLifecycleState.RECOVERY_EXECUTING,
                RecoveryLifecycleState.UNKNOWN,
            ):
                logger.warning(
                    f"[STATE] Recovery in {state_machine.recovery_state.value} state. No second side effect allowed."
                )
                return False, None, "RECOVERY_IN_PROGRESS_OR_UNKNOWN", None

            # Step 3: Record failure in state machine
            state_machine.on_failure_event()
            if state_machine.recovery_state == RecoveryLifecycleState.EXHAUSTED:
                logger.info(f"[POLICY] Retries exhausted for payment {payment_id}.")
                return False, None, "RETRIES_EXHAUSTED", None

            # Step 4: Decision Generation (Policy Engine Pre-filter + Predict + Score + Gate)
            decision = self.pipeline.decide(
                event_id=event_id,
                payment_id=payment_id,
                feature_snapshot_id=feature_snapshot_id,
                model_version=model_version,
                uplift_estimates=uplift_estimates,
                constraints=constraints,
                feature_staleness_seconds=feature_staleness_seconds,
            )

            final_action = decision.selected_action

            if final_action == RecoveryAction.DO_NOTHING:
                logger.info(f"[DECISION] Action is DO_NOTHING for {payment_id}. Safe no-op.")
                return True, None, "DO_NOTHING_SELECTED", decision

            # Step 5: Idempotency Record
            if not self.idempotency_store.record_decision(
                payment_id=payment_id,
                event_id=event_id,
                action=final_action.value,
                attempt_number=state_machine.attempt_count,
            ):
                logger.error(f"[IDEMPOTENCY] Conflicting decision for payment {payment_id} attempt {state_machine.attempt_count}. Aborting.")
                return False, None, "IDEMPOTENCY_CONFLICT", decision

            # Step 6: THE GOVERNING INVARIANT (Re-verify live state immediately prior to side-effect)
            live_status = live_state_fetcher(payment_id)
            if live_status in ("captured", "authorized", "paid"):
                logger.critical(
                    f"[GOVERNING INVARIANT] Payment {payment_id} live status is '{live_status}'! "
                    f"Aborting recommended side-effect ({final_action.value})."
                )
                state_machine.transition_payment(
                    PaymentLifecycleState.CAPTURED
                    if live_status == "captured"
                    else PaymentLifecycleState.AUTHORIZED
                )
                return False, None, "GOVERNING_INVARIANT_LIVE_STATE_CAPTURED", decision

            # Step 7: Transition to EXECUTING
            state_machine.begin_execution()

            # Step 8: Dispatch Execution
            idempotency_key = f"rec_{event_id}_{state_machine.attempt_count}"
            exec_record = RecoveryExecution(
                execution_id=f"exec_{event_id}",
                decision_id=event_id,
                payment_id=payment_id,
                order_id=order_id,
                action=final_action,
                status="dispatched",
                idempotency_key=idempotency_key,
            )

            result = self.executor.execute_action(
                decision=decision,
                amount_inr=amount_inr,
            )

            # Check if downstream timed out / failed
            if not result.get("success", True):
                error_msg = result.get("error", "UNKNOWN_ERROR")
                if "timeout" in error_msg.lower():
                    logger.warning(f"[TIMEOUT] Execution for {payment_id} timed out. Moving to UNKNOWN.")
                    state_machine.record_timeout_unknown()
                    exec_record.status = "unknown"
                    exec_record.error_message = error_msg
                    self.idempotency_store.record_execution(idempotency_key, exec_record.model_dump())
                    return False, exec_record, "EXECUTION_TIMEOUT_UNKNOWN", decision
                else:
                    logger.error(f"[EXECUTION] Execution failed: {error_msg}")
                    exec_record.status = "failed"
                    exec_record.error_message = error_msg
                    state_machine.transition_recovery(RecoveryLifecycleState.FAILED)
                    self.idempotency_store.record_execution(idempotency_key, exec_record.model_dump())
                    return False, exec_record, "EXECUTION_FAILED", decision

            # Succeeded dispatch
            exec_record.status = "succeeded"
            exec_record.api_response = result.get("api_response")
            self.idempotency_store.record_execution(idempotency_key, exec_record.model_dump())

            return True, exec_record, "ACTION_DISPATCHED", decision

        finally:
            self.idempotency_store.release_lock(payment_id)
