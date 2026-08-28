# Rally Architecture

The Rally backend is designed as a rigorous, defensible, causal-decisioning pipeline wrapped in a strict safety state-machine.

## Core Principles
1. **Idempotency**: All executions are uniquely keyed to `(payment_id, attempt_number)`.
2. **Governing Invariant**: A live state check is performed immediately prior to any side-effecting action. If a payment is CAPTURED or AUTHORIZED, the action is unconditionally vetoed.
3. **Safe Degraded Mode**: If the ML pipeline crashes, outputs NaNs, or receives stale features, the decision silently falls back to a safe rule-based baseline or DO_NOTHING.
4. **Causal Validity**: The deployable model (`TLearner`) operates strictly on observables. The Oracle model is physically separated.

## Domain Driven Design

* `domain/`: Contains immutable schemas (Pydantic models and Enums). These are the language of the system.
* `features/`: The feature extraction pipeline, which must save point-in-time snapshots to ensure ML reproducibility.
* `models/`: The ML rankers (T-Learner, DPL).
* `policy/`: The engine that takes ML outputs and applies economic scaling (GMV * Prob - Cost), then applies hard safety vetoes.
* `safety/`: The `RecoveryCoordinator`, `PaymentStateMachine`, and `IdempotencyStore`. The heart of the system.
* `execution/`: Adapters to Razorpay and UNKNOWN reconciliation services.

## Execution Pipeline

1. **Trigger**: Webhook or manual poll triggers `RecoveryCoordinator`.
2. **Lock**: `IdempotencyStore` acquires a lock on `payment_id`.
3. **Verify State**: Verify payment is not terminal.
4. **Predict & Score**: `DecisionPipeline` builds features, predicts probabilities, scales by economics.
5. **Gate**: Policy vetoes unsafe actions.
6. **Double-Check**: Governing invariant live check against Razorpay.
7. **Dispatch**: Action sent to `ExecutionAdapter`.
8. **Reconcile**: If timeout, moved to `UNKNOWN`. Handled asynchronously by `ReconciliationService`.
