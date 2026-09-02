# Rally Threat Model & Safety Guarantees

## 1. Double-Charge Prevention
**Threat**: The system sends a recovery link to a customer who has already successfully paid via a different channel, resulting in the customer paying twice.
**Mitigation**: The `Governing Invariant`. Immediately before the API dispatch, the `RecoveryCoordinator` polls the canonical gateway for the live status. If it is `CAPTURED` or `AUTHORIZED`, the pipeline aborts.

## 2. Thundering Herd / Concurrency Conflicts
**Threat**: Multiple webhooks for the same failure arrive simultaneously, causing the system to dispatch multiple duplicate recovery actions.
**Mitigation**: Thread-safe distributed locking via `IdempotencyStore`. The first worker acquires a lock on `payment_id`. Subsequent workers fail to acquire and drop the event.

## 3. Replay Attacks / Late Webhooks
**Threat**: An attacker replays old webhooks, or the gateway delivers a webhook 3 days late, causing a stale nudge to be sent.
**Mitigation**: HMAC SHA256 signature verification guarantees integrity. A strict staleness check (e.g., max 300 seconds) drops any webhook older than the threshold.

## 4. Model Hallucination / Corruption
**Threat**: The ML model throws an exception, returns NaNs for uplift, or predicts negative costs.
**Mitigation**: The `DecisionPipeline` catches all ML-layer exceptions and degrades cleanly to a deterministic Rule-Based baseline (or `DO_NOTHING`), ensuring the service never crashes and never dispatches unsafe outputs.

## 5. Idempotency Leaks (UNKNOWN State)
**Threat**: An API request to Razorpay times out. The system doesn't know if the link was sent. It retries, resulting in spam.
**Mitigation**: The state machine enforces an `UNKNOWN` state. No further actions can be taken until the `ReconciliationService` explicitly polls Razorpay and resolves the UNKNOWN state to `SUCCEEDED` or `FAILED`.
