# Scientific Boundaries and Causal Evaluation Framework

This document serves as the authoritative source of truth for the scientific and causal boundaries of the Rally system. These boundaries are immutable and must never be compromised by production code, evaluation logic, or demo presentation.

## 1. Information Boundaries

### 1.1 Observable Information (Deployable)
The deployable Rally decisioning pipeline may ONLY access information that is explicitly observable *before* a recovery action is taken.
This includes:
* `amount_inr` (Payment amount)
* `error_code` (Bank/Gateway failure reason)
* `merchant_id` (Identifier of the merchant)
* `user_tier` (Customer account tier, e.g., Basic, Premium)
* `action` (The action taken, available for off-policy evaluation)
* `propensity` (The probability of the action taken, available for off-policy evaluation)
* `recovered` (The outcome, available *after* the fact for training/evaluation)

### 1.2 Latent Simulator-Only Information (Non-Deployable)
The simulator generates the following latent variables representing the true counterfactual potential outcomes. **These must NEVER be accessible to the deployable ML pipeline or policy engine:**
* `_latent_self_cure_prob` (Base probability of recovery if no action is taken)
* `_latent_tau_{action}` (The true causal uplift of a specific action)
* `_latent_p_{action}` (The true probability of recovery for a specific action)

## 2. Component Boundaries

### 2.1 Deployable Components
The `TLearnerUpliftModel` and the standard `PaymentPulsePolicy` (the internal policy class) are deployable in Rally. They learn exclusively from `Observable Information` (historical logs of contexts, actions, and outcomes) using Doubly Robust or Inverse Propensity methods.

### 2.2 Oracle-Only Components
The `OraclePolicyModel` (formerly DPL) and `OraclePolicy` are diagnostic components only. They have omniscient access to `Latent Simulator-Only Information` to calculate the theoretical absolute maximum recovery value.
**Rule:** The Oracle must never be imported by deployable production decisioning code.

## 3. Data Boundaries

### 3.1 Training & Validation Data
Used exclusively for fitting the `TLearnerUpliftModel`, tuning hyperparameters, or training the evaluation reward models (for DR estimation).

### 3.2 Held-Out Test Data
A completely isolated cohort (e.g., `seed=44`).
**Rule:** Held-out test outcomes must NEVER influence training, threshold tuning, model selection, or feature engineering. We do not tune models based on their test-set performance to artificially win against baselines.

## 4. Causal Assumptions

The causal estimates (Uplift, DR ENRV) rely on the following standard assumptions. In production, these are assumptions; in this simulator, they are guaranteed by the data generating process:
1. **Unconfoundedness (Conditional Exchangeability):** All variables affecting both the action assignment and the outcome are observed (captured in the context).
2. **Positivity (Overlap):** Every action has a non-zero probability of being selected for every context. (In the simulator, we enforce an `epsilon` exploration rate).
3. **Consistency (SUTVA):** The outcome of one payment failure is unaffected by the treatment assigned to another payment failure (no interference), and there are no hidden variations of the treatments.

## 5. Current Scientific Results & Unsupported Claims

### 5.1 Immutable Fact: Current Deployable Performance
As of the latest scientifically rigorous evaluation, the deployable `TLearnerUpliftModel` **DOES NOT beat the rule-based baseline** in the simulator ground truth. 
* Ground Truth ENRV (Rally): ~286 INR/event
* Ground Truth ENRV (Rule-Based): ~336 INR/event

### 5.2 Rules for Presentation
* **DO NOT** hide this negative ML result.
* **DO NOT** tune the system (simulator economics, test cohorts, features) toward a positive result just to make the demo look better.
* **DO NOT** claim that synthetic evaluation establishes real-world production revenue lift.
* **DO NOT** call the T-Learner "unbiased" in finite, highly confounded samples.

The architectural value of Rally lies in its safe state machine, off-policy causal evaluation framework, and robust failure recovery pipeline—not in manufacturing a false positive ML result on synthetic data.
