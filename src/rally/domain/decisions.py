from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field
from rally.domain.enums import RecoveryAction, DecisionReason

def utcnow():
    return datetime.now(timezone.utc)

class ModelPrediction(BaseModel):
    """Raw output from the ML layer before economic scaling."""
    model_version: str
    action_probabilities: dict[RecoveryAction, float] = Field(description="P(Recovery|Action) per arm")
    action_uplifts: dict[RecoveryAction, float] = Field(description="τ̂(Action) = P(R|A) - P(R|Control)")
    confidence: float = Field(ge=0.0, le=1.0)
    
class EconomicValue(BaseModel):
    """Translated economic values."""
    action: RecoveryAction
    expected_recovered_gmv: float
    expected_recovered_contribution: float
    intervention_cost: float
    enrv: float = Field(description="Expected Net Recovered Value")

class PolicyDecision(BaseModel):
    """The final decision payload orchestrated by the Policy layer."""
    decision_id: str
    payment_id: str
    model_version: str
    feature_snapshot_id: str
    candidate_actions: list[RecoveryAction]
    
    # ML details (Optional if degraded)
    predicted_effect: Optional[float] = None
    predicted_probability: Optional[float] = None
    
    # Economics details (Optional if degraded/fallback)
    expected_recovered_gmv: Optional[float] = None
    expected_recovered_contribution: Optional[float] = None
    intervention_cost: Optional[float] = None
    enrv: Optional[float] = None
    
    # Decision details
    selected_action: RecoveryAction
    policy_reason: DecisionReason
    confidence: Optional[float] = None
    degraded_mode: bool = False
    timestamp: datetime = Field(default_factory=utcnow)
