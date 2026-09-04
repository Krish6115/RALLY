# Out-of-Sample Evaluation Summary

Rally strictly separates the `SyntheticDataGenerator`'s latent ground-truth variables (the "Oracle") from the deployable model.

## Evaluation Results

Evaluated on a held-out test cohort, the Doubly Robust estimator indicates:
- **No Recovery:** 0.0 INR ENRV/event
- **Rule-Based (Incumbent):** 331.54 INR ENRV/event (95% CI: 280.12, 382.96)
- **Rally:** 303.44 INR ENRV/event (95% CI: -78.50, 685.38)

## Conclusion & Promotion Status
**NOT PROMOTED.** The current deployable model does not establish statistical superiority over the rule-based baseline due to insufficient mutual information between pre-decision observable features and the latent propensity to self-cure. 
