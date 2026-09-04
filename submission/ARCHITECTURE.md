# Rally System Architecture

The Rally system strictly decouples analytical machine learning from determinisitic side-effect execution.

## High-Level Flow
1. **Event Ingestion:** `payment.failed` webhook is securely ingested and decoded.
2. **Feature Extraction:** `ContextBuilder` aggregates pre-decision observable features.
3. **ML Prediction:** `TLearnerUpliftModel` predicts the conditional average treatment effect (CATE) of each action on recovery probability.
4. **Economic Scoring:** `ActionRanker` translates the uplift probabilities into an Expected Net Recovered Value (ENRV) using static transaction amounts and intervention costs.
5. **Safety Gate:** `RecoveryCoordinator` executes the Governing Invariant by fetching live status and checking the `IdempotencyStore`.
6. **Execution:** Safe actions are handed to `ExecutionAdapter` which performs the API side effect and emits observability metrics.
7. **Reconciliation:** (Background) Handles edge cases where execution lands in an `UNKNOWN` state.
