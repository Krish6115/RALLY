import pytest
import json
from datetime import datetime, timezone

from paymentpulse.domain.decisions import PolicyDecision
from paymentpulse.domain.enums import RecoveryAction, DecisionReason

def test_frontend_serialization():
    """
    Proves that the PolicyDecision object exposes a flat, stable JSON structure
    suitable for the frontend without leaking internal objects.
    """
    decision = PolicyDecision(
        decision_id="evt_123",
        payment_id="pay_123",
        model_version="v1",
        feature_snapshot_id="snap_123",
        candidate_actions=[RecoveryAction.RETRY_NOW, RecoveryAction.SEND_PAYMENT_LINK],
        predicted_effect=0.05,
        predicted_probability=0.10,
        expected_recovered_gmv=50.0,
        expected_recovered_contribution=45.0,
        intervention_cost=2.5,
        enrv=42.5,
        selected_action=RecoveryAction.SEND_PAYMENT_LINK,
        policy_reason=DecisionReason.MODEL_RECOMMENDATION,
        confidence=0.85,
        degraded_mode=False,
        timestamp=datetime(2026, 9, 3, 12, 0, 0, tzinfo=timezone.utc)
    )
    
    # Must be natively JSON serializable via pydantic model_dump_json
    json_str = decision.model_dump_json()
    data = json.loads(json_str)
    
    assert data["decision_id"] == "evt_123"
    assert data["payment_id"] == "pay_123"
    assert data["selected_action"] == "send_payment_link"
    assert data["policy_reason"] == "model_recommendation"
    assert data["enrv"] == 42.5
    assert data["degraded_mode"] is False
    assert "timestamp" in data
