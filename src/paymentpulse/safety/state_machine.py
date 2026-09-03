"""
Payment & Recovery State Machine.

Enforces strict lifecycle transitions and invariants:
- Terminal states (CAPTURED, REFUNDED, EXHAUSTED, TERMINATED) cannot transition.
- UNKNOWN outcomes must be explicitly reconciled before any subsequent action.
- CAPTURED is terminal for recovery side effects.
- Out-of-order or duplicate transitions fail closed.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


class InvalidStateTransitionError(Exception):
    """Raised when an illegal state transition is attempted."""
    pass


class PaymentLifecycleState(str, enum.Enum):
    """Razorpay official payment states."""
    CREATED = "created"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    FAILED = "failed"
    REFUNDED = "refunded"

    @property
    def is_terminal_success(self) -> bool:
        return self in {PaymentLifecycleState.CAPTURED, PaymentLifecycleState.AUTHORIZED}

    @property
    def is_terminal(self) -> bool:
        return self in {PaymentLifecycleState.CAPTURED, PaymentLifecycleState.REFUNDED}


class RecoveryLifecycleState(str, enum.Enum):
    """PaymentPulse recovery lifecycle states."""
    IDLE = "idle"
    FAILED = "failed"
    RECOVERY_PENDING = "recovery_pending"
    RECOVERY_EXECUTING = "recovery_executing"
    UNKNOWN = "unknown"
    RECOVERED = "recovered"
    EXHAUSTED = "exhausted"
    TERMINATED = "terminated"

    @property
    def is_terminal(self) -> bool:
        return self in {
            RecoveryLifecycleState.RECOVERED,
            RecoveryLifecycleState.EXHAUSTED,
            RecoveryLifecycleState.TERMINATED,
        }

    @property
    def allows_new_action(self) -> bool:
        return self in {
            RecoveryLifecycleState.FAILED,
            RecoveryLifecycleState.RECOVERY_PENDING,
        }


# Strict Transition Matrix: current_state -> set of allowed next states
VALID_RECOVERY_TRANSITIONS: dict[RecoveryLifecycleState, set[RecoveryLifecycleState]] = {
    RecoveryLifecycleState.IDLE: {
        RecoveryLifecycleState.FAILED,
        RecoveryLifecycleState.TERMINATED,
    },
    RecoveryLifecycleState.FAILED: {
        RecoveryLifecycleState.RECOVERY_PENDING,
        RecoveryLifecycleState.EXHAUSTED,
        RecoveryLifecycleState.TERMINATED,
        RecoveryLifecycleState.RECOVERED,  # Natural self-cure
    },
    RecoveryLifecycleState.RECOVERY_PENDING: {
        RecoveryLifecycleState.RECOVERY_EXECUTING,
        RecoveryLifecycleState.EXHAUSTED,
        RecoveryLifecycleState.TERMINATED,
        RecoveryLifecycleState.RECOVERED,  # Self-cure before dispatch
    },
    RecoveryLifecycleState.RECOVERY_EXECUTING: {
        RecoveryLifecycleState.RECOVERED,
        RecoveryLifecycleState.FAILED,
        RecoveryLifecycleState.UNKNOWN,
        RecoveryLifecycleState.TERMINATED,
    },
    RecoveryLifecycleState.UNKNOWN: {
        RecoveryLifecycleState.RECOVERED,
        RecoveryLifecycleState.FAILED,
        RecoveryLifecycleState.TERMINATED,
        RecoveryLifecycleState.EXHAUSTED,
    },
    # Terminal states have NO allowed transitions
    RecoveryLifecycleState.RECOVERED: set(),
    RecoveryLifecycleState.EXHAUSTED: set(),
    RecoveryLifecycleState.TERMINATED: set(),
}


@dataclass
class PaymentStateMachine:
    """
    Manages payment state and associated recovery lifecycle.
    """
    payment_id: str
    order_id: str
    payment_state: PaymentLifecycleState = PaymentLifecycleState.CREATED
    recovery_state: RecoveryLifecycleState = RecoveryLifecycleState.IDLE
    attempt_count: int = 0
    max_retries: int = 3
    last_transition_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    history: list[tuple[datetime, str, str]] = field(default_factory=list)

    def transition_payment(self, new_state: PaymentLifecycleState) -> None:
        """
        Transition canonical payment state.
        If payment becomes CAPTURED or AUTHORIZED, unconditionally terminate recovery!
        """
        # Terminal payment state cannot change (except authorized -> captured/refunded)
        if self.payment_state == PaymentLifecycleState.CAPTURED:
            if new_state != PaymentLifecycleState.REFUNDED:
                raise InvalidStateTransitionError(
                    f"Payment {self.payment_id} is CAPTURED. Cannot transition to {new_state.value}."
                )
        if self.payment_state == PaymentLifecycleState.REFUNDED:
            raise InvalidStateTransitionError(
                f"Payment {self.payment_id} is REFUNDED. Cannot transition to {new_state.value}."
            )

        old_state = self.payment_state
        self.payment_state = new_state
        self._record_history(f"payment:{old_state.value}", f"payment:{new_state.value}")

        # The Governing Invariant: CAPTURED or AUTHORIZED terminates any active recovery
        if new_state.is_terminal_success:
            if not self.recovery_state.is_terminal:
                self.force_terminate(
                    reason=f"Payment transitioned to terminal success state: {new_state.value}"
                )

    def transition_recovery(self, new_state: RecoveryLifecycleState) -> None:
        """
        Transition recovery lifecycle state according to the transition matrix.
        """
        # If payment is already captured/settled, recovery can NEVER move to an active state
        if self.payment_state.is_terminal_success and new_state in {
            RecoveryLifecycleState.RECOVERY_PENDING,
            RecoveryLifecycleState.RECOVERY_EXECUTING,
            RecoveryLifecycleState.FAILED,
        }:
            raise InvalidStateTransitionError(
                f"Cannot transition recovery to {new_state.value} when payment is {self.payment_state.value}."
            )

        if self.recovery_state.is_terminal:
            raise InvalidStateTransitionError(
                f"Recovery is in terminal state {self.recovery_state.value}. Cannot transition to {new_state.value}."
            )

        allowed = VALID_RECOVERY_TRANSITIONS.get(self.recovery_state, set())
        if new_state not in allowed:
            raise InvalidStateTransitionError(
                f"Illegal transition: {self.recovery_state.value} -> {new_state.value}. "
                f"Allowed transitions: {[s.value for s in allowed]}"
            )

        old_state = self.recovery_state
        self.recovery_state = new_state
        self.last_transition_time = datetime.now(timezone.utc)
        self._record_history(f"recovery:{old_state.value}", f"recovery:{new_state.value}")

    def on_failure_event(self) -> None:
        """Triggered when a payment attempt fails."""
        self.attempt_count += 1
        self.payment_state = PaymentLifecycleState.FAILED

        if self.recovery_state == RecoveryLifecycleState.IDLE:
            self.transition_recovery(RecoveryLifecycleState.FAILED)

        if self.attempt_count >= self.max_retries:
            self.transition_recovery(RecoveryLifecycleState.EXHAUSTED)
        else:
            if self.recovery_state == RecoveryLifecycleState.FAILED:
                self.transition_recovery(RecoveryLifecycleState.RECOVERY_PENDING)

    def begin_execution(self) -> None:
        """Call when an action is dispatched."""
        if self.payment_state.is_terminal_success:
            raise InvalidStateTransitionError(
                f"Governing Invariant violated: Cannot execute recovery for {self.payment_state.value} payment."
            )
        self.transition_recovery(RecoveryLifecycleState.RECOVERY_EXECUTING)

    def record_timeout_unknown(self) -> None:
        """Call when downstream API call times out with unknown outcome."""
        self.transition_recovery(RecoveryLifecycleState.UNKNOWN)

    def reconcile_unknown(self, actual_status: str) -> None:
        """Explicit reconciliation for UNKNOWN outcome."""
        if self.recovery_state != RecoveryLifecycleState.UNKNOWN:
            raise InvalidStateTransitionError(
                f"Cannot reconcile from non-UNKNOWN state: {self.recovery_state.value}"
            )
        if actual_status in ("captured", "authorized"):
            self.payment_state = (
                PaymentLifecycleState.CAPTURED
                if actual_status == "captured"
                else PaymentLifecycleState.AUTHORIZED
            )
            self.transition_recovery(RecoveryLifecycleState.RECOVERED)
        elif actual_status == "failed":
            if self.attempt_count >= self.max_retries:
                self.transition_recovery(RecoveryLifecycleState.EXHAUSTED)
            else:
                self.transition_recovery(RecoveryLifecycleState.FAILED)
        else:
            raise ValueError(f"Unrecognized reconciliation status: {actual_status}")

    def force_terminate(self, reason: str = "") -> None:
        """Immediately terminate recovery (e.g. customer opt-out, manual abort, payment already paid)."""
        old = self.recovery_state
        self.recovery_state = RecoveryLifecycleState.TERMINATED
        self.last_transition_time = datetime.now(timezone.utc)
        self._record_history(f"recovery:{old.value}", f"recovery:terminated ({reason})")

    def _record_history(self, from_state: str, to_state: str) -> None:
        self.history.append((datetime.now(timezone.utc), from_state, to_state))
