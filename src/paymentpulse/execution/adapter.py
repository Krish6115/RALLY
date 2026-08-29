"""
Razorpay Integration Boundary (Phase 17).

Defines the abstract contract for side-effect execution and provides:
1. LiveRazorpayAdapter (Production)
2. MockRazorpayAdapter (Testing/Development)
3. SimulatorAdapter (Offline Evaluation)
"""

from __future__ import annotations
import logging
import random
import time
from abc import ABC, abstractmethod
from typing import Any

from paymentpulse.domain.decisions import PolicyDecision
from paymentpulse.domain.enums import RecoveryAction
from paymentpulse.observability.metrics import MetricsClient

logger = logging.getLogger(__name__)

class ExecutionAdapter(ABC):
    @abstractmethod
    def execute_action(self, decision: PolicyDecision, amount_inr: float) -> dict[str, Any]:
        """Executes the side-effect and returns the result dictionary."""
        pass
        
    @abstractmethod
    def fetch_live_status(self, payment_id: str) -> str:
        """Fetches the canonical live state for the Governing Invariant."""
        pass

class MockRazorpayAdapter(ExecutionAdapter):
    """Safe mock adapter for local development and testing."""
    def __init__(self, metrics: MetricsClient, simulate_timeouts: bool = False):
        self.metrics = metrics
        self.simulate_timeouts = simulate_timeouts
        # payment_id -> status
        self._mock_states: dict[str, str] = {}

    def execute_action(self, decision: PolicyDecision, amount_inr: float) -> dict[str, Any]:
        start = time.time()
        logger.info(f"[MOCK EXEC] Simulating {decision.selected_action.value} for {decision.payment_id}")
        
        # Simulate network latency
        time.sleep(0.05)
        
        # Simulate timeouts if requested
        if self.simulate_timeouts:
            latency = (time.time() - start) * 1000
            self.metrics.emit_execution(decision.payment_id, decision.selected_action.value, "timeout", latency)
            return {"success": False, "error": "API timeout (mock)"}
            
        latency = (time.time() - start) * 1000
        self.metrics.emit_execution(decision.payment_id, decision.selected_action.value, "success", latency)
        
        return {
            "success": True,
            "api_response": {"mock_id": "resp_123", "status": "dispatched"}
        }

    def fetch_live_status(self, payment_id: str) -> str:
        # Default to failed if we don't know it, allows recovery to proceed
        return self._mock_states.get(payment_id, "failed")
        
    def set_mock_state(self, payment_id: str, status: str):
        self._mock_states[payment_id] = status
