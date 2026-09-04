"""
Structured Observability and Metrics.

Implements Phase 15:
- Emits structured JSON events for decisions and execution outcomes.
- Collects simulated latency measurements.
"""

from __future__ import annotations
import json
import logging
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)

class MetricsClient:
    def __init__(self, stdout: bool = True):
        self.stdout = stdout

    def emit_decision(self, payment_id: str, decision_dict: dict[str, Any]) -> None:
        """Emit a structured decision event."""
        event = {
            "event_type": "decision",
            "payment_id": payment_id,
            "timestamp": time.time(),
            "payload": decision_dict
        }
        self._emit(event)

    def emit_execution(self, payment_id: str, action: str, outcome: str, latency_ms: float) -> None:
        """Emit an execution outcome with latency."""
        event = {
            "event_type": "execution",
            "payment_id": payment_id,
            "action": action,
            "outcome": outcome,
            "latency_ms": latency_ms,
            "timestamp": time.time()
        }
        self._emit(event)
        
    def _emit(self, event: dict[str, Any]) -> None:
        if self.stdout:
            # We can parse these structured logs in our log aggregator later
            print(f"[METRICS] {json.dumps(event)}")
