"""
Thread-safe Idempotency and Concurrency Lock Store.

Implements Section K, Row 15 & Section 7/8 Audit:
- True thread-safe concurrency lock with lease expiration
- Idempotency key tracking for decisions, executions, and webhooks
- Reentrancy and context manager support
- Atomic compare-and-swap
"""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger(__name__)


class IdempotencyStore:
    """
    Manages decision/execution idempotency and concurrent distributed/in-memory locking.
    Thread-safe implementation using reentrant locks and timestamped leases.
    """

    def __init__(self, default_lease_seconds: float = 30.0):
        self._lock = threading.RLock()
        self.default_lease_seconds = default_lease_seconds

        # payment_id -> lock_expiration_timestamp
        self._active_locks: dict[str, float] = {}

        # (payment_id, attempt_number) -> (event_id, action, timestamp)
        self._decisions: dict[tuple[str, int], tuple[str, str, float]] = {}

        # idempotency_key -> execution_result_dict
        self._executions: dict[str, dict] = {}

        # webhook_event_id -> received_timestamp
        self._seen_webhook_events: dict[str, float] = {}

    def acquire_lock(self, payment_id: str, lease_seconds: Optional[float] = None) -> bool:
        """
        Thread-safely attempt to acquire an exclusive lock for this payment.
        Returns True if acquired, False if already held by an unexpired lease.
        """
        lease = lease_seconds or self.default_lease_seconds
        now = time.time()

        with self._lock:
            if payment_id in self._active_locks:
                expiration = self._active_locks[payment_id]
                if now < expiration:
                    # Lock is still held and valid
                    return False
                else:
                    logger.warning(
                        f"Lock on {payment_id} expired at {expiration} (current {now}). Stealing lock."
                    )

            self._active_locks[payment_id] = now + lease
            return True

    def release_lock(self, payment_id: str) -> None:
        """Release the lock if held."""
        with self._lock:
            self._active_locks.pop(payment_id, None)

    @contextmanager
    def lock(self, payment_id: str, lease_seconds: Optional[float] = None):
        """Context manager for acquiring and safely releasing a lock."""
        acquired = self.acquire_lock(payment_id, lease_seconds)
        if not acquired:
            raise RuntimeError(f"Could not acquire lock for payment {payment_id} — concurrent operation in progress.")
        try:
            yield
        finally:
            self.release_lock(payment_id)

    def record_decision(
        self,
        payment_id: str,
        event_id: str,
        action: str,
        attempt_number: int = 1,
    ) -> bool:
        """
        Record a side-effecting decision atomically per (payment_id, attempt_number).
        Returns False if a conflicting decision already exists for this attempt.
        """
        now = time.time()
        key = (payment_id, attempt_number)
        with self._lock:
            if key in self._decisions:
                existing_event, existing_action, _ = self._decisions[key]
                if existing_event != event_id:
                    logger.error(
                        f"Idempotency conflict for payment {payment_id} (attempt {attempt_number}). "
                        f"Existing decision: {existing_event} ({existing_action}), "
                        f"Attempted new: {event_id} ({action}). Failing closed."
                    )
                    return False
                return True

            self._decisions[key] = (event_id, action, now)
            return True

    def record_execution(
        self,
        idempotency_key: str,
        result: dict,
    ) -> bool:
        """Record an execution result by its idempotency key."""
        with self._lock:
            if idempotency_key in self._executions:
                return False
            self._executions[idempotency_key] = result
            return True

    def get_execution(self, idempotency_key: str) -> Optional[dict]:
        with self._lock:
            return self._executions.get(idempotency_key)

    def is_webhook_seen(self, event_id: str) -> bool:
        with self._lock:
            return event_id in self._seen_webhook_events

    def mark_webhook_seen(self, event_id: str) -> bool:
        """Mark webhook as seen. Returns True if first time seen, False if duplicate."""
        now = time.time()
        with self._lock:
            if event_id in self._seen_webhook_events:
                return False
            self._seen_webhook_events[event_id] = now
            return True

    def clear(self) -> None:
        """Reset the store (for testing)."""
        with self._lock:
            self._active_locks.clear(
                self._decisions.clear() or {}
            )
            self._executions.clear()
            self._seen_webhook_events.clear()
