# Policy Engine - Initial deterministic decision baseline
"""
The Orchestration Pipeline for PaymentPulse Decisioning.

This engine enforces the strict separation between:
1. Candidate Action Filtering (legal constraints)
2. ML Prediction (probabilities and uplift)
3. Economic Scoring (GMV, contribution, cost)
4. Deterministic Policy Gating (safety vetoes)
"""

from __future__ import annotations
import logging
from typing import Callable, Optional

from paymentpulse.domain.enums import RecoveryAction, DecisionReason, DegradedReason
from paymentpulse.domain.entities import AuditEvent
from paymentpulse.domain.decisions import ModelPrediction, EconomicValue, PolicyDecision
from paymentpulse.policy.constraints import PolicyConstraints
from paymentpulse.models.action_ranker import ActionRanker

logger = logging.getLogger(__name__)

class DecisionPipeline:
    """Orchestrates the decision flow."""

    def __init__(
        self,
        ml_predictor: Callable[[dict[str, float], list[RecoveryAction]], ModelPrediction],
        economic_scorer: Callable[[ModelPrediction, float], list[EconomicValue]],
        audit_callback: Optional[Callable[[AuditEvent], None]] = None,
    ):
        self.ml_predictor = ml_predictor
        self.economic_scorer = economic_scorer
        self.audit_callback = audit_callback

    def decide(
        self,
        event_id: str,
        payment_id: str,
        feature_snapshot_id: str,
        model_version: str,
        uplift_estimates: dict[str, float],
        constraints: PolicyConstraints,
        feature_staleness_seconds: float = 0.0,
        max_staleness_threshold: float = 60.0,
    ) -> PolicyDecision:
        """
        Executes the explicit pipeline: Filter -> Predict -> Score -> Gate -> Decide
        """
        # Step 1: Candidate Action Filter
        candidate_actions = constraints.get_legal_actions()
        
        degraded = False
        degraded_reason = DegradedReason.NONE
        
        # Stale feature check
        if feature_staleness_seconds > max_staleness_threshold:
            degraded = True
            degraded_reason = DegradedReason.STALE_FEATURES
        
        prediction = None
        economic_values = []
        best_eco = None
        
        # Step 2: ML Prediction (if not degraded)
        if not degraded:
            try:
                prediction = self.ml_predictor(uplift_estimates, candidate_actions)
                # Step 3: Economic Scoring
                economic_values = self.economic_scorer(prediction, constraints.transaction_amount_inr)
                if economic_values:
                    # Sort by ENRV descending
                    economic_values.sort(key=lambda x: x.enrv, reverse=True)
                    best_eco = economic_values[0]
            except Exception as e:
                logger.error(f"[SAFE DEGRADED MODE] ML model or scorer failure: {e}")
                degraded = True
                degraded_reason = DegradedReason.MODEL_ERROR
                if self.audit_callback:
                    self.audit_callback(AuditEvent(
                        audit_id=f"audit_deg_{event_id}",
                        event_type="DEGRADED_DECISION",
                        entity_id=payment_id,
                        payload={"error": str(e), "fallback": "do_nothing"}
                    ))
        
        # Step 4 & 5: Deterministic Policy Gate & Final Decision
        final_action = RecoveryAction.DO_NOTHING
        reason = DecisionReason.RULE_BASED_FALLBACK if degraded else DecisionReason.MODEL_RECOMMENDATION
        
        if not degraded and best_eco:
            if best_eco.enrv <= 0:
                final_action = RecoveryAction.DO_NOTHING
                reason = DecisionReason.SAFETY_VETO
            elif prediction and prediction.confidence < 0.1:
                final_action = RecoveryAction.DO_NOTHING
                reason = DecisionReason.LOW_CONFIDENCE
            else:
                final_action = best_eco.action
        
        # Hard Veto (The Governing Invariant)
        if constraints.payment_already_succeeded or constraints.payment_already_captured or constraints.order_already_paid:
            final_action = RecoveryAction.DO_NOTHING
            reason = DecisionReason.SAFETY_VETO

        return PolicyDecision(
            decision_id=event_id,
            payment_id=payment_id,
            model_version=model_version,
            feature_snapshot_id=feature_snapshot_id,
            candidate_actions=candidate_actions,
            predicted_effect=prediction.action_uplifts.get(final_action, 0.0) if prediction else None,
            predicted_probability=prediction.action_probabilities.get(final_action, 0.0) if prediction else None,
            expected_recovered_gmv=best_eco.expected_recovered_gmv if best_eco else None,
            expected_recovered_contribution=best_eco.expected_recovered_contribution if best_eco else None,
            intervention_cost=best_eco.intervention_cost if best_eco else None,
            enrv=best_eco.enrv if best_eco else None,
            selected_action=final_action,
            policy_reason=reason,
            confidence=prediction.confidence if prediction else None,
            degraded_mode=degraded
        )
