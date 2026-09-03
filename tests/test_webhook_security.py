import pytest
import hmac
import hashlib
import json
import time
from datetime import datetime, timezone

from paymentpulse.api.webhooks import WebhookReceiver
from paymentpulse.safety.idempotency import IdempotencyStore
from paymentpulse.domain.enums import WebhookEventType

def test_webhook_security_signature():
    secret = "test_secret_123"
    idempotency_store = IdempotencyStore()
    receiver = WebhookReceiver(secret=secret, idempotency_store=idempotency_store)
    
    payload = json.dumps({"event": "payment.failed"}).encode('utf-8')
    valid_signature = hmac.new(secret.encode('utf-8'), payload, hashlib.sha256).hexdigest()
    
    # Valid
    evt = receiver.process_incoming(
        event_id="evt_1",
        event_type_str="payment.failed",
        payload_body=payload,
        signature=valid_signature,
        created_at_timestamp=int(time.time())
    )
    assert evt.status == "verified"
    
    # Invalid
    evt_invalid = receiver.process_incoming(
        event_id="evt_2",
        event_type_str="payment.failed",
        payload_body=payload,
        signature="invalid_sig",
        created_at_timestamp=int(time.time())
    )
    assert evt_invalid.status == "rejected"
    assert evt_invalid.rejection_reason == "invalid_signature"

def test_webhook_staleness_and_idempotency():
    secret = "test_secret"
    receiver = WebhookReceiver(secret=secret, idempotency_store=IdempotencyStore(), max_staleness_seconds=300)
    
    payload = json.dumps({"event": "payment.failed"}).encode('utf-8')
    sig = hmac.new(secret.encode('utf-8'), payload, hashlib.sha256).hexdigest()
    
    now = time.time()
    
    # Stale
    evt_stale = receiver.process_incoming("evt_3", "payment.failed", payload, sig, int(now - 400))
    assert evt_stale.status == "rejected"
    assert evt_stale.rejection_reason == "stale_event"
    
    # Valid first time
    evt_valid = receiver.process_incoming("evt_4", "payment.failed", payload, sig, int(now))
    assert evt_valid.status == "verified"
    
    # Duplicate second time
    evt_dup = receiver.process_incoming("evt_4", "payment.failed", payload, sig, int(now))
    assert evt_dup.status == "rejected"
    assert evt_dup.rejection_reason == "duplicate"
