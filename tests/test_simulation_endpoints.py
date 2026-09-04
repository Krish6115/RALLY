from fastapi.testclient import TestClient
from src.rally.api.server import app
import pytest

client = TestClient(app)

def test_simulate_normal_failure():
    response = client.post("/api/simulate/failure", json={"scenario": "normal"})
    assert response.status_code == 200
    data = response.json()
    assert "event_id" in data
    assert data["payment_state"] == "failed"
    assert data["safety_decision"] == "ALLOW"
    assert data["degraded_reason"] == "none"

def test_simulate_timeout():
    response = client.post("/api/simulate/failure", json={"scenario": "timeout"})
    assert response.status_code == 200
    data = response.json()
    assert "event_id" in data
    assert data["recovery_state"] == "unknown"
    assert data["execution_outcome"] == "unknown"
    assert data["reconciliation_required"] is True

def test_simulate_late_capture():
    response = client.post("/api/simulate/failure", json={"scenario": "late_capture"})
    assert response.status_code == 200
    data = response.json()
    assert "event_id" in data
    assert data["safety_decision"] == "DENY"
    assert data["safety_reason"] == "GOVERNING_INVARIANT_LIVE_STATE_CAPTURED"

def test_simulate_stale_features():
    response = client.post("/api/simulate/failure", json={"scenario": "stale_features"})
    assert response.status_code == 200
    data = response.json()
    assert "event_id" in data
    assert data["degraded_reason"] == "stale_features"
    assert data["selected_action"] == "do_nothing"

