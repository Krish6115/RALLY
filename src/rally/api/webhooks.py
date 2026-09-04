"""
Webhook Receiver & Security Validation.

Implements Phase 8:
- Cryptographic HMAC signature validation.
- Staleness checking (rejecting delayed events).
- Deduplication via IdempotencyStore.
- Transformation into domain WebhookEvent.
"""

from __future__ import annotations
import hmac
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from rally.domain.entities import WebhookEvent
from rally.domain.enums import WebhookEventType
from rally.safety.idempotency import IdempotencyStore

logger = logging.getLogger(__name__)

class WebhookReceiver:
    def __init__(self, secret: str, idempotency_store: IdempotencyStore, max_staleness_seconds: float = 300.0):
        self.secret = secret.encode('utf-8')
        self.idempotency_store = idempotency_store
        self.max_staleness_seconds = max_staleness_seconds

    def verify_signature(self, payload_body: bytes, signature: str) -> bool:
        """Verify HMAC SHA256 signature."""
        expected = hmac.new(self.secret, payload_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def process_incoming(
        self,
        event_id: str,
        event_type_str: str,
        payload_body: bytes,
        signature: str,
        created_at_timestamp: int
    ) -> WebhookEvent:
        """Process, validate, and deduplicate an incoming webhook."""
        
        # 1. Signature check
        if not self.verify_signature(payload_body, signature):
            logger.warning(f"[WEBHOOK] Invalid signature for event {event_id}")
            return WebhookEvent(
                event_id=event_id,
                event_type=WebhookEventType.PAYMENT_FAILED, # Dummy fallback for rejected
                payload_body=payload_body,
                signature=signature,
                status="rejected",
                rejection_reason="invalid_signature"
            )
            
        # 2. Staleness check
        now = datetime.now(timezone.utc).timestamp()
        if (now - created_at_timestamp) > self.max_staleness_seconds:
            logger.warning(f"[WEBHOOK] Stale event {event_id} (age: {now - created_at_timestamp}s)")
            return WebhookEvent(
                event_id=event_id,
                event_type=WebhookEventType(event_type_str),
                payload_body=payload_body,
                signature=signature,
                status="rejected",
                rejection_reason="stale_event"
            )
            
        # 3. Deduplication
        if not self.idempotency_store.mark_webhook_seen(event_id):
            logger.info(f"[WEBHOOK] Duplicate event dropped: {event_id}")
            return WebhookEvent(
                event_id=event_id,
                event_type=WebhookEventType(event_type_str),
                payload_body=payload_body,
                signature=signature,
                status="rejected",
                rejection_reason="duplicate"
            )
            
        return WebhookEvent(
            event_id=event_id,
            event_type=WebhookEventType(event_type_str),
            payload_body=payload_body,
            signature=signature,
            status="verified"
        )
