import logging
from typing import Any
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sys
import os

# Ensure src is in path for relative imports if run directly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from paymentpulse.simulator import SyntheticDataGenerator
from paymentpulse.features.context_builder import ContextBuilder
from paymentpulse.models.uplift_model import TLearnerUpliftModel
from paymentpulse.models.action_ranker import ActionRanker
from paymentpulse.policy.engine import DecisionPipeline
from paymentpulse.policy.constraints import PolicyConstraints
from paymentpulse.domain.entities import MerchantPolicy
from paymentpulse.domain.decisions import ModelPrediction, EconomicValue
from paymentpulse.domain.enums import RecoveryAction
from paymentpulse.safety.state_machine import PaymentStateMachine, PaymentLifecycleState, RecoveryLifecycleState
from paymentpulse.safety.recovery_coordinator import RecoveryCoordinator
from paymentpulse.safety.idempotency import IdempotencyStore
from paymentpulse.execution.adapter import MockRazorpayAdapter
from paymentpulse.observability.metrics import MetricsClient
from paymentpulse.evaluation.runner import EvaluationRunner
from paymentpulse.models.baselines import RuleBasedPolicy, PaymentPulsePolicy

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Rally Demo Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global State
class ServerState:
    def __init__(self):
        self.sim = SyntheticDataGenerator(n_events=5000, seed=42)
        # We need a trained model for the pipeline
        logger.info("Generating training cohort...")
        df_train = self.sim.generate_batch()
        self.context_builder = ContextBuilder()
        X_train = self.context_builder.fit_transform(df_train)
        
        logger.info("Training T-Learner...")
        self.model = TLearnerUpliftModel()
        self.model.fit(X_train, df_train["action"].values, df_train["recovered"].values.astype(float))
        
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
            # We don't have the context dict here easily, so we just use the uplifts provided
            # Or make up a prediction
            action_uplifts = {a: uplifts.get(a.value, 0.05) for a in candidate_actions}
            action_probs = {a: 0.1 for a in candidate_actions}
            return ModelPrediction(
                model_version="mock_v1",
                action_probabilities=action_probs,
                action_uplifts=action_uplifts,
                confidence=0.9
            )
            
        self.pipeline = DecisionPipeline(
            ml_predictor=mock_predictor,
            economic_scorer=mock_scorer
        )
        
        self.idempotency = IdempotencyStore()
        self.metrics = MetricsClient(stdout=False)
        self.adapter = MockRazorpayAdapter(self.metrics, simulate_timeouts=False)
        self.coordinator = RecoveryCoordinator(self.pipeline, self.adapter, self.idempotency)
        
        self.events_feed = []
        self.overview_stats = {
            "failed_payments": 0,
            "estimated_enrv": 0.0,
            "decisions": 0,
            "safety_vetoes": 0,
            "unknown_outcomes": 0
        }

state = ServerState()

@app.get("/api/overview")
def get_overview():
    return state.overview_stats

@app.get("/api/feed")
def get_feed():
    # Return last 50 events, reversed (newest first)
    return state.events_feed[-50:][::-1]

class SimulationRequest(BaseModel):
    scenario: str

@app.post("/api/simulate/failure")
def simulate_failure(req: SimulationRequest):
    # Generate 1 event
    single_sim = SyntheticDataGenerator(n_events=1, seed=None)
    df_single = single_sim.generate_batch()
    row = df_single.iloc[0]
    
    payment_id = row['payment_id']
    order_id = row['order_id']
    amount = float(row['amount_inr'])
    error_code = row['error_code']
    method = row['method'].value if hasattr(row['method'], 'value') else row['method']
    
    import uuid
    event_id = f"evt_{uuid.uuid4().hex[:12]}"
    # Configure mock adapter based on scenario
    state.adapter.simulate_timeouts = (req.scenario == 'timeout')
    if req.scenario == 'late_capture':
        state.adapter.set_mock_state(payment_id, "captured")
    else:
        state.adapter.set_mock_state(payment_id, "failed")
        
    state_machine = PaymentStateMachine(payment_id=payment_id, order_id=order_id, max_retries=3)
    constraints = PolicyConstraints(transaction_amount_inr=amount)
    
    # Get feature dict
    features = {col: row[col] for col in df_single.columns if not col.startswith("_latent_") and "oracle" not in col.lower()}
    X_single = state.context_builder.transform(pd.DataFrame([features]))
    feature_dict = {name: val for name, val in zip(state.context_builder.feature_names, X_single[0])}
    
    # Run the coordinator which has the policy pipeline & safety gate
    committed, execution, reason, decision = state.coordinator.handle_payment_failure(
        event_id=event_id,
        payment_id=payment_id,
        order_id=order_id,
        amount_inr=amount,
        model_version="tlearner_v1",
        feature_snapshot_id=f"snap_{event_id}",
        uplift_estimates={"retry_now": 0.9, "send_email_link": 0.5},
        constraints=constraints,
        state_machine=state_machine,
        live_state_fetcher=state.adapter.fetch_live_status,
        feature_staleness_seconds=10.0 if req.scenario != 'stale_features' else 900.0
    )
    
    import datetime
    
    # Extract exact metrics for UI
    is_unknown = state_machine.recovery_state == RecoveryLifecycleState.UNKNOWN
    
    # Construct exact event contract for UI
    event_data = {
        "event_id": event_id,
        "payment_id": payment_id,
        "payment_state": state_machine.payment_state.value if hasattr(state_machine.payment_state, 'value') else str(state_machine.payment_state),
        "recovery_state": state_machine.recovery_state.value if hasattr(state_machine.recovery_state, 'value') else str(state_machine.recovery_state),
        "decision_id": getattr(decision, "decision_id", event_id),
        "selected_action": getattr(decision, "selected_action", None).value if decision else (execution.action.value if execution else "do_nothing"),
        "predicted_effect": getattr(decision, "predicted_effect", 0.0) or 0.0,
        "enrv": getattr(decision, "enrv", 0.0) or 0.0,
        "safety_decision": "ALLOW" if committed else "DENY",
        "safety_reason": reason,
        "execution_outcome": getattr(execution, "status", "none"),
        "degraded_reason": "stale_features" if getattr(decision, "degraded_mode", False) else "none",
        "reconciliation_required": is_unknown,
        "timestamp": datetime.datetime.now().isoformat(),
        # Retain for backward compatibility in UI / Feed details
        "amount": amount,
        "method": str(method),
        "error_code": error_code,
        "predicted_enrv": getattr(decision, "enrv", 0.0) or 0.0,
        "safety_result": "committed" if committed else "vetoed",
        "veto_reason": reason,
        "execution_state": state_machine.recovery_state.value if hasattr(state_machine.recovery_state, 'value') else str(state_machine.recovery_state),
        "features": feature_dict,
        "action_rankings": [
            {
                "action": getattr(decision, "selected_action", None).value if decision else "do_nothing",
                "uplift": getattr(decision, "predicted_effect", 0.0) or 0.0,
                "expected_gmv": getattr(decision, "expected_recovered_gmv", 0.0) or 0.0,
                "expected_contribution": getattr(decision, "expected_recovered_contribution", 0.0) or 0.0,
                "cost": getattr(decision, "intervention_cost", 0.0) or 0.0,
                "enrv": getattr(decision, "enrv", 0.0) or 0.0
            }
        ] if decision and not getattr(decision, "degraded_mode", False) else []
    }
    
    state.events_feed.append(event_data)
    
    # Update KPIs
    state.overview_stats["failed_payments"] += 1
    state.overview_stats["decisions"] += 1
    if not committed and reason != "EXECUTION_TIMEOUT_UNKNOWN":
        state.overview_stats["safety_vetoes"] += 1
    if is_unknown:
        state.overview_stats["unknown_outcomes"] += 1
    if committed:
        state.overview_stats["estimated_enrv"] += (getattr(decision, 'enrv', 0.0) or 0.0)
        
    return event_data

@app.get("/api/decision/{payment_id}")
def get_decision(payment_id: str):
    for evt in state.events_feed:
        if evt["payment_id"] == payment_id:
            return evt
    raise HTTPException(status_code=404, detail="Decision not found")

@app.get("/api/evaluation")
def get_evaluation():
    # Provide static honest evaluation metrics from Phase 23 audit
    return {
        "disclaimer": EvaluationRunner.DISCLAIMER,
        "is_promoted": False,
        "reason": "Held-out simulation does not establish superiority over incumbent strategy.",
        "results": [
            {
                "Policy": "No Recovery",
                "GT ENRV/Event": 0.0,
                "DR ENRV/Event (Est)": 0.0,
                "DR 95% CI (Est)": "[0.0, 0.0]",
                "Intervention Rate": "0.0%",
            },
            {
                "Policy": "Rule-Based",
                "GT ENRV/Event": 335.99,
                "DR ENRV/Event (Est)": 331.54,
                "DR 95% CI (Est)": "[280.12, 382.96]",
                "Intervention Rate": "100.0%",
            },
            {
                "Policy": "Rally",
                "GT ENRV/Event": 286.38,
                "DR ENRV/Event (Est)": 303.44,
                "DR 95% CI (Est)": "[-78.50, 685.38]",
                "Intervention Rate": "44.2%",
            }
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
