import pytest
from rally.safety.state_machine import (
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

    sm.on_failure_event()
    assert sm.payment_state == PaymentLifecycleState.FAILED
    assert sm.recovery_state == RecoveryLifecycleState.RECOVERY_PENDING

    sm.begin_execution()
    assert sm.recovery_state == RecoveryLifecycleState.RECOVERY_EXECUTING

    sm.transition_payment(PaymentLifecycleState.CAPTURED)
    assert sm.payment_state == PaymentLifecycleState.CAPTURED
    assert sm.recovery_state == RecoveryLifecycleState.TERMINATED

def test_captured_blocks_execution():
    """Governing invariant: Cannot execute recovery against a captured payment."""
    sm = PaymentStateMachine(payment_id="pay_002", order_id="order_002")
    sm.transition_payment(PaymentLifecycleState.CAPTURED)

    with pytest.raises(InvalidStateTransitionError):
        sm.begin_execution()

def test_unknown_outcome_requires_reconciliation():
    """UNKNOWN state cannot transition directly to executing; must be reconciled."""
    sm = PaymentStateMachine(payment_id="pay_003", order_id="order_003")
    sm.on_failure_event()
    sm.begin_execution()
    sm.record_timeout_unknown()
    
    assert sm.recovery_state == RecoveryLifecycleState.UNKNOWN

    with pytest.raises(InvalidStateTransitionError):
        sm.begin_execution()

    sm.reconcile_unknown("captured")
    assert sm.recovery_state == RecoveryLifecycleState.RECOVERED
    assert sm.payment_state == PaymentLifecycleState.CAPTURED

def test_terminal_states_cannot_transition():
    """Terminal recovery states cannot transition."""
    sm = PaymentStateMachine(payment_id="pay_005", order_id="order_005")
    sm.force_terminate("customer_opt_out")
    assert sm.recovery_state == RecoveryLifecycleState.TERMINATED

    with pytest.raises(InvalidStateTransitionError):
        sm.transition_recovery(RecoveryLifecycleState.RECOVERY_PENDING)
