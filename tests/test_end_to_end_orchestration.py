import pytest
import time
from typing import Callable, Any

from rally.domain.entities import (
    Customer, Order, Payment, PaymentFailure, MerchantPolicy, 
    PaymentMethod, ErrorSource, RecoveryAction
)
from rally.domain.enums import PaymentStatus, RecoveryState, ExecutionOutcome
from rally.domain.decisions import PolicyDecision, ModelPrediction, EconomicValue
from rally.policy.constraints import PolicyConstraints
from rally.policy.engine import DecisionPipeline
from rally.safety.state_machine import PaymentStateMachine, RecoveryLifecycleState
from rally.safety.idempotency import IdempotencyStore
from rally.safety.recovery_coordinator import RecoveryCoordinator
from rally.execution.adapter import MockRazorpayAdapter
from rally.observability.metrics import MetricsClient
from rally.execution.reconciliation import ReconciliationService

# ---------------------------------------------------------
# Mocks
# ---------------------------------------------------------

def mock_ml_predictor(uplifts, actions):
    return ModelPrediction(
        model_version="test_v1",
        action_probabilities={a: 0.8 for a in actions},
        action_uplifts={a: 0.1 for a in actions},
        confidence=0.9
    )

def mock_economic_scorer(pred, amount):
    return [
        EconomicValue(
            action=RecoveryAction.RETRY_NOW,
            expected_recovered_gmv=amount * 0.8,
            expected_recovered_contribution=amount * 0.8 * 0.9,
            intervention_cost=0.5,
            enrv=(amount * 0.8 * 0.9) - 0.5
        )
    ]

# ---------------------------------------------------------
# Fixtures
# ---------------------------------------------------------

@pytest.fixture
def idempotency():
    return IdempotencyStore()

@pytest.fixture
def metrics():
    return MetricsClient(stdout=False)

@pytest.fixture
def adapter(metrics):
    return MockRazorpayAdapter(metrics)

@pytest.fixture
def pipeline():
    return DecisionPipeline(
        ml_predictor=mock_ml_predictor,
        economic_scorer=mock_economic_scorer
    )

@pytest.fixture
def coordinator(pipeline, adapter, idempotency):
    return RecoveryCoordinator(
        policy=pipeline,
        action_executor=adapter,
        idempotency_store=idempotency
    )

@pytest.fixture
def state_machine():
    return PaymentStateMachine(payment_id="pay_123", order_id="order_123")

@pytest.fixture
def constraints():
    return PolicyConstraints(
        transaction_amount_inr=1000.0
    )

# ---------------------------------------------------------
# Tests
# ---------------------------------------------------------

def test_real_orchestration_path(coordinator, state_machine, constraints, adapter):
    """
    Tests the explicit production-style pipeline path without mocking internal components.
    """
    adapter.set_mock_state("pay_123", "failed")
    
    committed, execution, reason, decision = coordinator.handle_payment_failure(
        event_id="evt_1",
        payment_id="pay_123",
        order_id="order_123",
        amount_inr=1000.0,
        model_version="test_v1",
        feature_snapshot_id="snap_1",
        uplift_estimates={"retry_now": 0.1},
        constraints=constraints,
        state_machine=state_machine,
        live_state_fetcher=adapter.fetch_live_status,
        feature_staleness_seconds=10.0
    )
    
    assert committed is True
    assert execution is not None
    assert execution.action == RecoveryAction.RETRY_NOW
    assert execution.status == "succeeded"
    assert state_machine.recovery_state == RecoveryLifecycleState.RECOVERY_EXECUTING
    assert state_machine.attempt_count == 1

def test_negative_governing_invariant_captured(coordinator, state_machine, constraints, adapter):
    """
    Proves the system refuses to act if the payment is already CAPTURED in real time.
    """
    # Live state says captured!
    adapter.set_mock_state("pay_123", "captured")
    
    committed, execution, reason, decision = coordinator.handle_payment_failure(
        event_id="evt_1",
        payment_id="pay_123",
        order_id="order_123",
        amount_inr=1000.0,
        model_version="test_v1",
        feature_snapshot_id="snap_1",
        uplift_estimates={"retry_now": 0.1},
        constraints=constraints,
        state_machine=state_machine,
        live_state_fetcher=adapter.fetch_live_status,
        feature_staleness_seconds=10.0
    )
    
    assert committed is False
    assert reason == "GOVERNING_INVARIANT_LIVE_STATE_CAPTURED"
    assert state_machine.recovery_state == RecoveryLifecycleState.TERMINATED

def test_negative_duplicate_request_idempotency(coordinator, state_machine, constraints, adapter):
    """
    Proves duplicate attempts are blocked by the IdempotencyStore.
    """
    adapter.set_mock_state("pay_123", "failed")
    
    coordinator.handle_payment_failure(
        event_id="evt_1", payment_id="pay_123", order_id="order_123",
        amount_inr=1000.0, model_version="test_v1", feature_snapshot_id="snap_1",
        uplift_estimates={}, constraints=constraints, state_machine=state_machine,
        live_state_fetcher=adapter.fetch_live_status
    )
    
    # Try again with same event
    committed, _, reason, _ = coordinator.handle_payment_failure(
        event_id="evt_1", payment_id="pay_123", order_id="order_123",
        amount_inr=1000.0, model_version="test_v1", feature_snapshot_id="snap_1",
        uplift_estimates={}, constraints=constraints, state_machine=state_machine,
        live_state_fetcher=adapter.fetch_live_status
    )
    
    assert committed is False
    assert reason == "RECOVERY_IN_PROGRESS_OR_UNKNOWN"

def test_stale_features_degraded_fallback(pipeline, constraints):
    """
    Proves the Policy Engine safely degrades if features are stale.
    """
    decision = pipeline.decide(
        event_id="evt_2",
        payment_id="pay_123",
        feature_snapshot_id="snap_2",
        model_version="test_v1",
        uplift_estimates={},
        constraints=constraints,
        feature_staleness_seconds=100.0,  # STALE
        max_staleness_threshold=60.0
    )
    
    assert decision.degraded_mode is True
    assert decision.selected_action == RecoveryAction.DO_NOTHING
