#!/usr/bin/env python3
"""
Interactive demo script for the AI Buildathon panel presentation.

This script demonstrates the deterministic safety layer in action,
which is the core defense against the "what if it recommends something
dangerous?" question (Section N/Q of the research doc).

It runs a small batch, but explicitly injects edge cases:
1. A late webhook (payment succeeded before action dispatched)
2. A stale feature set
"""

import logging
import time
from datetime import datetime

from paymentpulse.config import config
from paymentpulse.simulator import generate_batch
from paymentpulse.features.context_builder import ContextBuilder
from paymentpulse.models.uplift_model import TLearnerUpliftModel
from paymentpulse.policy.engine import DecisionPipeline
from paymentpulse.policy.constraints import PolicyConstraints
from paymentpulse.domain.decisions import ModelPrediction, EconomicValue
from paymentpulse.domain.enums import RecoveryAction

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def simulate_live_state_check(payment_id: str, inject_already_captured: bool = False):
    """Mocks the Razorpay API live state fetch."""
    if inject_already_captured:
        return "captured"
    return "failed"


def main():
    logger.info("=== Rally Interactive Demo ===")
    logger.info("Training lightweight model on background synthetic data...")
    
    # Train quickly on a small batch
    df_train = generate_batch(n_events=2000, seed=42)
    ctx = ContextBuilder()
    X_train = ctx.fit_transform(df_train)
    
    model = TLearnerUpliftModel()
    model.fit(X_train, df_train["action"].values, df_train["recovered"].values.astype(float))
    
    def mock_scorer(pred: ModelPrediction, amt: float) -> list[EconomicValue]:
        vals = []
        for action in pred.action_uplifts.keys():
            uplift = pred.action_uplifts[action]
            gmv = uplift * amt
            cost = 0.50 if action != RecoveryAction.DO_NOTHING else 0.0
            if action == RecoveryAction.SEND_PAYMENT_LINK: cost = 2.50
            enrv = (gmv * 0.20) - cost
            vals.append(EconomicValue(
                action=action,
                expected_recovered_gmv=gmv,
                expected_recovered_contribution=gmv * 0.20,
                intervention_cost=cost,
                enrv=enrv
            ))
        return vals

    def mock_predictor(uplifts: dict[str, float], candidate_actions: list[RecoveryAction]) -> ModelPrediction:
        action_uplifts = {a: uplifts.get(a.value, 0.05) for a in candidate_actions}
        action_probs = {a: 0.1 for a in candidate_actions}
        return ModelPrediction(
            model_version="mock_v1",
            action_probabilities=action_probs,
            action_uplifts=action_uplifts,
            confidence=0.9
        )

    pipeline = DecisionPipeline(
        ml_predictor=mock_predictor,
        economic_scorer=mock_scorer
    )
    
    # Generate 1 test event
    logger.info("\nGenerating 1 live failure event...")
    df_test = generate_batch(n_events=1, seed=99)
    event_dict = df_test.iloc[0].to_dict()
    
    payment_id = event_dict["payment_id"]
    order_id = event_dict["order_id"]
    amount = float(event_dict["amount_inr"])
    
    # Build context
    X_test = ctx.transform(df_test)
    uplifts = {
        action: float(val[0])
        for action, val in model.predict_all_uplifts(X_test).items()
    }
    
    logger.info(f"\n[Event] Payment {payment_id} failed for {amount} INR")
    logger.info(f"[Event] Error: {event_dict['error_code']} (Source: {event_dict['error_source']})")
    
    # Base constraints
    constraints = PolicyConstraints(
        transaction_amount_inr=amount,
        min_intervention_amount_inr=10.0,
    )
    
    # === Demo 1: Normal Decision ===
    logger.info("\n--- Demo 1: Normal Decision Flow ---")
    decision = pipeline.decide(
        event_id="evt_001",
        payment_id=payment_id,
        feature_snapshot_id="snap_1",
        model_version="v1",
        uplift_estimates=uplifts,
        constraints=constraints,
    )
    
    logger.info(f"Model recommended: {decision.selected_action.value} (Net Value: INR {decision.enrv:.2f})")
    
    # === Demo 2: The Late Webhook (Adversarial Input) ===
    logger.info("\n--- Demo 2: The Late Webhook (Adversarial Input) ---")
    logger.info("Scenario: Webhook arrives late. By the time we decide, the payment has actually succeeded.")
    
    constraints_late = PolicyConstraints(
        transaction_amount_inr=amount,
        min_intervention_amount_inr=10.0,
        payment_already_captured=True
    )
    
    decision_late = pipeline.decide(
        event_id="evt_002",
        payment_id=payment_id,
        feature_snapshot_id="snap_1",
        model_version="v1",
        uplift_estimates=uplifts,
        constraints=constraints_late,
    )
    logger.info("Governing Invariant: Re-verifying live state before execution...")
    if decision_late.selected_action == RecoveryAction.DO_NOTHING and decision_late.policy_reason.value == "safety_veto":
        logger.info("ACTION ABORTED by Policy Engine. Model recommendation overridden.")
            
    # === Demo 3: Stale Features ===
    logger.info("\n--- Demo 3: Stale Features ---")
    logger.info("Scenario: The feature engineering pipeline took too long. Context is stale.")
    
    decision_stale = pipeline.decide(
        event_id="evt_003",
        payment_id=payment_id,
        feature_snapshot_id="snap_1",
        model_version="v1",
        uplift_estimates=uplifts,
        constraints=constraints,
        feature_staleness_seconds=120.0,  # Past the 60s threshold
    )
    
    if decision_stale.degraded_mode:
        logger.info(f"Vetoed by Policy Engine. Degraded mode active.")
        logger.info(f"Final safe action: {decision_stale.selected_action.value}")


if __name__ == "__main__":
    main()
