# Rally API Contract

The backend exposes a strictly defined boundary.

## 1. Webhook Ingestion (Async Trigger)

`POST /webhooks/razorpay`

Receives live payment failure events.

**Headers:**
`X-Razorpay-Signature`: HMAC SHA256 signature for verification.

**Body:** Standard Razorpay Webhook JSON

**Behavior:**
1. Validates signature.
2. Checks staleness.
3. Deduplicates via `IdempotencyStore`.
4. Asynchronously hands off to `RecoveryCoordinator`.

## 2. Manual Decision Trigger

`POST /decisions`

**Body:**
```json
{
  "payment_id": "pay_xyz",
  "order_id": "order_xyz",
  "amount_inr": 500.0,
  "error_code": "BAD_REQUEST_ERROR",
  "merchant_id": "merch_123"
}
```

**Behavior:**
Forces the evaluation pipeline for a specific payment synchronously (mostly for testing and demo).

## 3. Frontend Contract (Read-Only)

**Important**: The frontend is explicitly forbidden from modifying payment states or mutating the decision engine. The frontend serves solely as a diagnostic visualizer.

`GET /decisions/{payment_id}`
Returns the `DecisionRecord` and `ActionOutcome` for visualization.

All displayed ENRV (Expected Net Recovered Value) figures in the frontend MUST be labeled as "SIMULATED ENRV" to adhere to the Scientific Boundaries document.
