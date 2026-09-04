# Rally Failure Modes

1. **API Timeout:** Execution lands in `UNKNOWN`. `RecoveryCoordinator` halts all subsequent recovery attempts for the payment until reconciliation.
2. **Late Capture:** The user successfully completes payment on a separate tab while the webhook is processing. The deterministic safety gate intercepts this via the Live State fetch and vetoes the ML action.
3. **Stale Features:** System delay pushes the decision horizon > 60s. The system automatically activates a rule-based fallback and logs a degraded decision.
4. **Duplicate Webhook:** Caught by the `IdempotencyStore` lock. Action aborted.
