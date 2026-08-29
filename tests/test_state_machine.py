"""
Unit tests for PaymentStateMachine (Section 3 Audit).

Verifies:
- All legal state transitions
- Illegal transitions throw InvalidStateTransitionError
- CAPTURED is terminal for recovery side effects
- UNKNOWN outcome handling and reconciliation
- State monotonicity and terminal behavior
"""

import pytest
from paymentpulse.safety.state_machine import (
    PaymentStateMachine,
    PaymentLifecycleState,
    RecoveryLifecycleState,
    InvalidStateTransitionError,
)


def test_standard_recovery_flow():
    """FAILED -> RECOVERY_PENDING -> RECOVERY_EXECUTING -> RECOVERED"""
    sm = PaymentStateMachine(payment_id="pay_001", order_id="order_001")
    assert sm.payment_state == PaymentLifecycleState.CREATED
    assert sm.recovery_state == RecoveryLifecycleState.IDLE

    # Payment fails
    sm.on_failure_event()
    assert sm.payment_state == PaymentLifecycleState.FAILED
    assert sm.recovery_state == RecoveryLifecycleState.RECOVERY_PENDING

    # Recovery dispatched
    sm.begin_execution()
    assert sm.recovery_state == RecoveryLifecycleState.RECOVERY_EXECUTING

    # Payment recovers
    sm.transition_payment(PaymentLifecycleState.CAPTURED)
    assert sm.payment_state == PaymentLifecycleState.CAPTURED
    assert sm.recovery_state == RecoveryLifecycleState.TERMINATED


def test_captured_blocks_execution():
    """Governing invariant: Cannot execute recovery against a captured payment."""
    sm = PaymentStateMachine(payment_id="pay_002", order_id="order_002")
    sm.transition_payment(PaymentLifecycleState.CAPTURED)

    with pytest.raises(InvalidStateTransitionError):
        sm.begin_execution()

    with pytest.raises(InvalidStateTransitionError):
        sm.transition_recovery(RecoveryLifecycleState.RECOVERY_PENDING)


def test_unknown_outcome_requires_reconciliation():
    """UNKNOWN state cannot transition directly to executing; must be reconciled."""
    sm = PaymentStateMachine(payment_id="pay_003", order_id="order_003")
    sm.on_failure_event()
    sm.begin_execution()

    # External API timeout -> UNKNOWN
    sm.record_timeout_unknown()
    assert sm.recovery_state == RecoveryLifecycleState.UNKNOWN

    # Cannot jump back to executing without reconciliation
    with pytest.raises(InvalidStateTransitionError):
        sm.begin_execution()

    # Reconcile discovering success
    sm.reconcile_unknown("captured")
    assert sm.recovery_state == RecoveryLifecycleState.RECOVERED
    assert sm.payment_state == PaymentLifecycleState.CAPTURED


def test_unknown_reconciles_to_failure():
    """UNKNOWN state reconciled to failure allows subsequent recovery or exhausts."""
    sm = PaymentStateMachine(payment_id="pay_004", order_id="order_004", max_retries=2)
    sm.on_failure_event()  # attempt 1
    sm.begin_execution()
    sm.record_timeout_unknown()

    # Reconcile finding it actually failed
    sm.reconcile_unknown("failed")
    assert sm.recovery_state == RecoveryLifecycleState.FAILED

    # Next attempt triggers exhaustion when limit reached
    sm.on_failure_event()  # attempt 2
    assert sm.recovery_state == RecoveryLifecycleState.EXHAUSTED


def test_terminal_states_cannot_transition():
    """Terminal recovery states (RECOVERED, EXHAUSTED, TERMINATED) cannot transition."""
    sm = PaymentStateMachine(payment_id="pay_005", order_id="order_005")
    sm.force_terminate("customer_opt_out")
    assert sm.recovery_state == RecoveryLifecycleState.TERMINATED

    with pytest.raises(InvalidStateTransitionError):
        sm.transition_recovery(RecoveryLifecycleState.RECOVERY_PENDING)


def test_captured_payment_cannot_revert_to_failed():
    """Out-of-order payment.failed webhook after payment is captured is rejected."""
    sm = PaymentStateMachine(payment_id="pay_006", order_id="order_006")
    sm.transition_payment(PaymentLifecycleState.CAPTURED)

    with pytest.raises(InvalidStateTransitionError):
        sm.transition_payment(PaymentLifecycleState.FAILED)
