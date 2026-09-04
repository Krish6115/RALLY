import concurrent.futures
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

def test_true_concurrency_exactly_one_action_committed():
    """
    Spawns 10 concurrent threads all attempting recovery on the exact same payment_id simultaneously.
    Asserts EXACTLY ONE side-effecting recovery action is committed.
    """
    idempotency_store = IdempotencyStore()
    metrics = MetricsClient(stdout=False)
    adapter = MockRazorpayAdapter(metrics)
    
    # Overwrite the execution to track counts
    call_count = 0
    original_exec = adapter.execute_action
    
    def tracked_exec(decision, amount_inr):
        nonlocal call_count
        call_count += 1
        return original_exec(decision, amount_inr)
        
    adapter.execute_action = tracked_exec

    pipeline = DecisionPipeline(
        ml_predictor=mock_ml_predictor,
        economic_scorer=mock_economic_scorer
    )
    
    coordinator = RecoveryCoordinator(pipeline, adapter, idempotency_store)
    
    payment_id = "pay_race_condition_999"
    order_id = "order_race_999"
    amount = 2500.0

    state_machine = PaymentStateMachine(payment_id=payment_id, order_id=order_id, max_retries=3)
    constraints = PolicyConstraints(
        transaction_amount_inr=amount
    )

    num_workers = 10
    results = []

    def worker_task(worker_id: int):
        event_id = f"evt_race_{worker_id}"
        return coordinator.handle_payment_failure(
            event_id=event_id, payment_id=payment_id, order_id=order_id,
            amount_inr=amount, model_version="test_v1", feature_snapshot_id="snap_1",
            uplift_estimates={}, constraints=constraints, state_machine=state_machine,
            live_state_fetcher=lambda pid: "failed"
        )

    # Execute all 10 workers concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as pool:
        futures = [pool.submit(worker_task, i) for i in range(num_workers)]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    # Tally outcomes
    successful_commits = [r for r in results if r[0] is True]
    rejected_attempts = [r for r in results if r[0] is False]

    # Exactly 1 succeeds, 9 fail
    assert len(successful_commits) == 1
    assert len(rejected_attempts) == num_workers - 1
    assert call_count == 1
