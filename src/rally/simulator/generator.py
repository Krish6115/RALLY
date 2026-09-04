"""
Latent-truth synthetic data generator.

This is the most critical component in the entire project. If the simulator
is flawed, every downstream result is meaningless.

Design principles (from Section H/I of research doc):
1. LATENT TRUTH MODEL: The simulator has ground-truth customer/environment
   state that determines real recovery probabilities. The ML model never
   sees this state directly — only noisy observable features.
2. ANTI-LEAKAGE: Features available to the model are noisy projections of
   latent state. Error codes and attempt history are realistic signals;
   customer_id or direct latent parameters are never exposed.
3. CALIBRATION: Self-cure rates, recovery rates, and treatment effects are
   calibrated to published numbers (NPCI, Razorpay blog, industry data).
4. LOGGING POLICY: Epsilon-greedy (ε=0.1) gives known propensities for
   off-policy evaluation. Without known propensities, counterfactual
   evaluation is impossible.
5. CAUSAL STRUCTURE: Outcomes are generated from do(A=a), not P(Y|A=a).
   The simulator IS the causal model, so there's no confounding in the
   *generated* data — confounding only arises if you train a naive
   supervised model on the logged (non-random) actions, which is exactly
   the mistake Section I warns against.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

from rally.domain.enums import PaymentMethod, ErrorSource, RecoveryAction
from .models import (
    CustomerProfile,
    MerchantPolicy,
    FailureEvent,
    PaymentAttempt,
    DecisionRecord,
    ActionOutcome,
    EventContext,
)
from .error_taxonomy import ERROR_CATALOG, ErrorCodeEntry
from .downtime import DowntimeSimulator


class SyntheticDataGenerator:
    """
    Generates synthetic payment failure events with realistic, causally-correct
    recovery outcomes.

    The generator produces (context, action, propensity, outcome) tuples that
    form a logged bandit feedback dataset — the correct input format for
    off-policy evaluation and contextual bandit training.
    """

    # UPI TPAPs (Third Party Application Providers) and common instruments
    UPI_APPS = ["gpay", "phonepe", "paytm", "bhim", "cred", "amazonpay"]
    CARD_BINS = ["411111", "524000", "372835", "600001", "508227"]
    BANKS = DowntimeSimulator.BANKS

    def __init__(
        self,
        n_events: int = 10_000,
        seed: int = 42,
        epsilon: float = 0.1,
        merchant_policy: Optional[MerchantPolicy] = None,
        contribution_margin: float = 1.0,
    ):
        self.n_events = n_events
        self.seed = seed
        self.epsilon = epsilon
        self.contribution_margin = contribution_margin
        self.rng = np.random.default_rng(seed)
        self.merchant_policy = merchant_policy or MerchantPolicy()
        self.downtime_sim = DowntimeSimulator(self.rng)

        # Pre-compute error code sampling weights
        self._error_weights = np.array([e.frequency_weight for e in ERROR_CATALOG])
        self._error_weights /= self._error_weights.sum()

    def generate_batch(self) -> pd.DataFrame:
        """
        Generate a full batch of failure events with logged actions and outcomes.

        Returns a DataFrame with columns for:
        - Context features (observable by the model)
        - Logged action and propensity (for off-policy evaluation)
        - Outcome (recovery, value, self-cure flag)
        - Latent state (for ground-truth analysis, NOT for model training)
        """
        records = []
        for i in range(self.n_events):
            record = self._generate_one_event(i)
            records.append(record)

        df = pd.DataFrame(records)
        return df

    def _generate_one_event(self, index: int) -> dict:
        """Generate one complete (context, action, propensity, outcome) tuple."""

        # --- Step 1: Generate latent customer profile ---
        customer = self._generate_customer()

        # --- Step 2: Generate the payment attempt (observable) ---
        attempt = self._generate_attempt(customer)

        # --- Step 3: Get error entry for ground truth ---
        error_entry = self._sample_error(attempt.method)

        # Update attempt with the sampled error
        attempt.error_code = error_entry.code
        attempt.error_source = error_entry.source
        attempt.error_description = error_entry.description

        # --- Step 4: Build failure event context ---
        hour_of_day = attempt.timestamp.hour + attempt.timestamp.minute / 60.0
        provider = self._get_provider_for_attempt(attempt)
        downtime_mod = self.downtime_sim.get_downtime_modifier(provider, hour_of_day)

        is_gateway_down = downtime_mod["self_cure_multiplier"] < 1.0
        downtime_severity = 1.0 - downtime_mod["self_cure_multiplier"]

        prior_attempts = self.rng.choice([0, 1, 2, 3], p=[0.6, 0.25, 0.10, 0.05])

        event = FailureEvent(
            attempt=attempt,
            customer=customer,
            merchant_policy=self.merchant_policy,
            is_gateway_down=is_gateway_down,
            is_bank_down=is_gateway_down and error_entry.source == ErrorSource.BANK,
            downtime_severity=downtime_severity,
            prior_attempts_this_session=prior_attempts,
            time_since_session_start_seconds=self.rng.exponential(120),
        )

        # --- Step 5: Compute ground-truth self-cure and treatment effects ---
        self_cure_prob = self._compute_self_cure_probability(
            error_entry, customer, downtime_mod
        )
        treatment_effects = self._compute_treatment_effects(
            error_entry, customer, downtime_mod, attempt, prior_attempts
        )

        # --- Step 6: Select action via epsilon-greedy logging policy ---
        action, propensity = self._logging_policy(
            error_entry, treatment_effects, event
        )

        # --- Step 7: Generate outcome under do(A=action) ---
        outcome = self._generate_outcome(
            action, self_cure_prob, treatment_effects, attempt, customer
        )

        # --- Step 8: Flatten to a record ---
        return self._flatten_record(
            index, event, error_entry, action, propensity,
            outcome, self_cure_prob, treatment_effects,
            hour_of_day, downtime_mod
        )

    def _generate_customer(self) -> CustomerProfile:
        """Generate a latent customer profile."""
        return CustomerProfile(
            customer_id=f"cust_{uuid.uuid4().hex[:12]}",
            self_cure_propensity=self.rng.beta(3, 7),  # Mean ~0.3
            nudge_responsiveness=self.rng.beta(4, 6),  # Mean ~0.4
            method_switch_willingness=self.rng.beta(2, 5),  # Mean ~0.28
            fatigue_rate=self.rng.beta(1, 15),  # Mean ~0.06, low
            purchase_intent=self.rng.beta(5, 3),  # Mean ~0.625, skewed high
        )

    def _generate_attempt(self, customer: CustomerProfile) -> PaymentAttempt:
        """Generate a payment attempt with realistic characteristics."""
        # Method distribution (India-centric: UPI dominant)
        method_value = self.rng.choice(
            [m.value for m in PaymentMethod],
            p=[0.55, 0.25, 0.12, 0.08]  # UPI, Card, Netbanking, Wallet
        )
        method = PaymentMethod(method_value)

        # Amount distribution — log-normal, capped
        amount = min(float(self.rng.lognormal(mean=6.5, sigma=1.2)), 100_000)
        amount = max(amount, 10.0)
        amount = round(amount, 2)

        # Instrument
        if method == PaymentMethod.UPI:
            instrument = self.rng.choice(self.UPI_APPS)
        elif method == PaymentMethod.CARD:
            instrument = self.rng.choice(self.CARD_BINS)
        else:
            instrument = self.rng.choice(self.BANKS)

        # Timestamp — uniform over 24 hours, slight peak at evening
        hour = self.rng.normal(loc=18, scale=5) % 24
        minute = self.rng.integers(0, 60)
        timestamp = datetime(2026, 8, 15, int(hour), int(minute), 0)

        session_id = f"sess_{uuid.uuid4().hex[:12]}"
        order_id = f"order_{uuid.uuid4().hex[:12]}"
        payment_id = f"pay_{uuid.uuid4().hex[:12]}"

        return PaymentAttempt(
            payment_id=payment_id,
            order_id=order_id,
            session_id=session_id,
            amount_inr=amount,
            method=method,
            instrument=instrument,
            error_code="PLACEHOLDER",  # Will be filled by error sampling
            error_source=ErrorSource.CUSTOMER,
            attempt_number=1,
            timestamp=timestamp,
            session_start=timestamp - timedelta(seconds=self.rng.exponential(60)),
        )

    def _sample_error(self, method: PaymentMethod) -> ErrorCodeEntry:
        """Sample an error code, filtered by payment method."""
        applicable = [
            (i, e) for i, e in enumerate(ERROR_CATALOG)
            if method in e.applicable_methods
        ]
        if not applicable:
            applicable = list(enumerate(ERROR_CATALOG))

        indices, entries = zip(*applicable)
        weights = np.array([self._error_weights[i] for i in indices])
        weights /= weights.sum()

        choice_idx = self.rng.choice(len(entries), p=weights)
        return entries[choice_idx]

    def _get_provider_for_attempt(self, attempt: PaymentAttempt) -> str:
        """Map an attempt to its primary provider for downtime checking."""
        if attempt.method == PaymentMethod.UPI:
            # Map UPI app to a bank
            return self.rng.choice(self.BANKS)
        elif attempt.method == PaymentMethod.CARD:
            return self.rng.choice(self.BANKS)
        else:
            return self.rng.choice(self.BANKS)

    def _compute_self_cure_probability(
        self,
        error_entry: ErrorCodeEntry,
        customer: CustomerProfile,
        downtime_mod: dict[str, float],
    ) -> float:
        """
        Compute P(recover | X, do(A=∅)) — the probability this failure
        self-cures with NO intervention.

        This is the baseline against which all treatment effects are measured.
        """
        base = error_entry.base_self_cure_rate

        # Customer-specific modulation
        customer_mod = (
            0.5 * customer.self_cure_propensity +
            0.3 * customer.purchase_intent +
            0.2 * 0.5  # Base
        )
        p = base * customer_mod * 2.0  # Scale to keep in reasonable range

        # Downtime effect
        p *= downtime_mod["self_cure_multiplier"]

        return float(np.clip(p, 0.01, 0.60))

    def _compute_treatment_effects(
        self,
        error_entry: ErrorCodeEntry,
        customer: CustomerProfile,
        downtime_mod: dict[str, float],
        attempt: PaymentAttempt,
        prior_attempts: int,
    ) -> dict[str, float]:
        """
        Compute τ_true(X, a) for each action — the causal treatment effect.

        These are the TRUE incremental recovery probabilities above self-cure.
        The model's job is to learn approximations of these from logged data.
        """
        profile = error_entry.treatment_profile
        effects = {}

        for action in RecoveryAction:
            if action == RecoveryAction.DO_NOTHING:
                effects[action.value] = 0.0
                continue

            base_effect = profile.get(action)

            # Customer-specific modulation
            if action == RecoveryAction.SEND_PAYMENT_LINK:
                base_effect *= (0.5 + 0.5 * customer.nudge_responsiveness)
            elif action in (RecoveryAction.SWITCH_UPI_APP, RecoveryAction.SWITCH_TO_CARD):
                base_effect *= (0.3 + 0.7 * customer.method_switch_willingness)
            elif action == RecoveryAction.RETRY_NOW:
                # Diminishing returns on retries
                retry_decay = max(0.1, 1.0 - 0.3 * prior_attempts)
                base_effect *= retry_decay
            elif action in RecoveryAction.wait_actions():
                # Wait is more effective for patient, high-intent customers
                base_effect *= (0.4 + 0.6 * customer.purchase_intent)

            # Downtime modulation
            if action == RecoveryAction.RETRY_NOW:
                base_effect *= downtime_mod["retry_multiplier"]
            elif action in RecoveryAction.wait_actions():
                base_effect *= downtime_mod["wait_multiplier"]
            elif action in (RecoveryAction.SWITCH_UPI_APP, RecoveryAction.SWITCH_TO_CARD):
                base_effect *= downtime_mod["switch_multiplier"]

            # Amount modulation: larger amounts → slightly lower treatment effect
            # (higher-value transactions have more friction)
            amount_mod = 1.0 / (1.0 + attempt.amount_inr / 10000.0)
            base_effect *= (0.5 + 0.5 * amount_mod)

            # Add noise to prevent perfect predictability
            noise = self.rng.normal(0, 0.02)
            base_effect = float(np.clip(base_effect + noise, 0.0, 0.35))

            effects[action.value] = base_effect

        return effects

    def _logging_policy(
        self,
        error_entry: ErrorCodeEntry,
        treatment_effects: dict[str, float],
        event: FailureEvent,
    ) -> tuple[RecoveryAction, float]:
        """
        Epsilon-greedy logging policy.

        With probability (1 - ε): follow the rule-based policy (Baseline 3)
        With probability ε: random uniform over all legal actions

        Returns (action, propensity) — propensity is crucial for off-policy eval.
        """
        # Get legal actions (respecting merchant policy constraints)
        legal_actions = self._get_legal_actions(event)

        if not legal_actions:
            return RecoveryAction.DO_NOTHING, 1.0

        n_legal = len(legal_actions)
        rule_action = error_entry.rule_based_action

        # If rule action isn't legal, default to do_nothing
        if rule_action not in legal_actions:
            rule_action = RecoveryAction.DO_NOTHING
            if RecoveryAction.DO_NOTHING not in legal_actions:
                rule_action = legal_actions[0]

        # Epsilon-greedy selection
        if self.rng.random() < self.epsilon:
            # Random
            action_idx = self.rng.choice(len(legal_actions))
            action = legal_actions[action_idx]
            # Propensity: ε/n for each random choice, plus (1-ε) if it happens
            # to be the rule-based action too
            propensity = self.epsilon / n_legal
            if action == rule_action:
                propensity += (1 - self.epsilon)
        else:
            # Greedy (follow rule-based policy)
            action = rule_action
            propensity = (1 - self.epsilon) + self.epsilon / n_legal

        return action, float(propensity)

    def _get_legal_actions(self, event: FailureEvent) -> list[RecoveryAction]:
        """Get actions that pass merchant policy hard constraints."""
        policy = event.merchant_policy
        legal = [RecoveryAction.DO_NOTHING]  # Always legal

        # Check opt-out
        if event.customer.customer_id in policy.opt_out_customer_ids:
            return legal  # Only do_nothing is legal

        # Check retry limit
        if event.prior_attempts_this_session < policy.max_retries:
            legal.append(RecoveryAction.RETRY_NOW)

        # Wait actions (always legal if session hasn't expired)
        remaining_time = (
            15 * 60 -  # 15-minute session timeout
            event.time_since_session_start_seconds
        )
        if remaining_time > 120:
            legal.append(RecoveryAction.WAIT_2MIN)
        if remaining_time > 300:
            legal.append(RecoveryAction.WAIT_5MIN)
        if remaining_time > 600:
            legal.append(RecoveryAction.WAIT_10MIN)

        # Method switch
        if PaymentMethod.UPI in policy.allowed_methods:
            legal.append(RecoveryAction.SWITCH_UPI_APP)
        if PaymentMethod.CARD in policy.allowed_methods:
            legal.append(RecoveryAction.SWITCH_TO_CARD)

        # Payment link (needs a channel)
        if policy.allowed_channels:
            legal.append(RecoveryAction.SEND_PAYMENT_LINK)

        # Human escalation
        if policy.allow_human_escalation:
            legal.append(RecoveryAction.ESCALATE_TO_HUMAN)

        # Amount threshold
        if event.attempt.amount_inr < policy.min_intervention_amount_inr:
            # Below threshold — only allow do_nothing and retry (low-cost)
            legal = [a for a in legal if a in (
                RecoveryAction.DO_NOTHING,
                RecoveryAction.RETRY_NOW,
            )]

        return legal

    def _generate_outcome(
        self,
        action: RecoveryAction,
        self_cure_prob: float,
        treatment_effects: dict[str, float],
        attempt: PaymentAttempt,
        customer: CustomerProfile,
    ) -> dict:
        """
        Generate the causal outcome under do(A=action).

        The outcome probability is:
            P(recover) = self_cure_prob + τ(X, action)
        clamped to [0, 1].

        This is causal (interventional) because the simulator IS the
        structural causal model — there's no confounding in generation.
        """
        treatment_effect = treatment_effects.get(action.value, 0.0)
        p_recover = float(np.clip(self_cure_prob + treatment_effect, 0.0, 0.95))

        recovered = bool(self.rng.random() < p_recover)

        # Determine if it was a self-cure
        was_self_cure = False
        if recovered and action == RecoveryAction.DO_NOTHING:
            was_self_cure = True
        elif recovered and self.rng.random() < (self_cure_prob / max(p_recover, 1e-9)):
            # Even with an action, some recoveries are self-cures
            was_self_cure = True

        # Compute costs
        cost = self._compute_action_cost(action)

        # Compute net value incorporating contribution margin
        recovered_amount = attempt.amount_inr if recovered else 0.0
        recovered_contribution = recovered_amount * self.contribution_margin
        net_value = recovered_contribution - cost

        # Time to outcome
        if action in RecoveryAction.wait_actions():
            wait_minutes = {"wait_2min": 2, "wait_5min": 5, "wait_10min": 10}
            base_time = wait_minutes[action.value] * 60
            time_to_outcome = base_time + self.rng.exponential(30)
        elif recovered:
            time_to_outcome = self.rng.exponential(120)  # ~2 min average
        else:
            time_to_outcome = 15 * 60  # Session timeout

        return {
            "recovered": recovered,
            "recovered_amount": recovered_amount,
            "was_self_cure": was_self_cure,
            "intervention_cost": cost,
            "net_value": net_value,
            "time_to_outcome": time_to_outcome,
            "p_recover": p_recover,
        }

    def _compute_action_cost(self, action: RecoveryAction) -> float:
        """
        Compute the cost of an action.

        Costs include:
        - Direct channel cost (SMS, WhatsApp, email)
        - Modeled friction/fatigue cost
        - Human escalation cost
        """
        cost_map = {
            RecoveryAction.DO_NOTHING: 0.0,
            RecoveryAction.RETRY_NOW: 0.10,  # Minimal — API call only
            RecoveryAction.WAIT_2MIN: 0.0,
            RecoveryAction.WAIT_5MIN: 0.0,
            RecoveryAction.WAIT_10MIN: 0.0,
            RecoveryAction.SWITCH_UPI_APP: 0.50,  # Link/notification cost
            RecoveryAction.SWITCH_TO_CARD: 0.50,
            RecoveryAction.SEND_PAYMENT_LINK: 2.50,  # SMS/WhatsApp + friction
            RecoveryAction.ESCALATE_TO_HUMAN: 25.0,  # Agent time
        }
        return cost_map.get(action, 0.0)

    def _flatten_record(
        self,
        index: int,
        event: FailureEvent,
        error_entry: ErrorCodeEntry,
        action: RecoveryAction,
        propensity: float,
        outcome: dict,
        self_cure_prob: float,
        treatment_effects: dict[str, float],
        hour_of_day: float,
        downtime_mod: dict[str, float],
    ) -> dict:
        """
        Flatten a complete event into a flat dictionary for DataFrame creation.

        Columns are separated into:
        - OBSERVABLE features (prefix: none) — what the model can see
        - LOGGED action/outcome — what was done and what happened
        - LATENT ground truth (prefix: _latent_) — for analysis ONLY, never model input
        """
        attempt = event.attempt

        record = {
            # === EVENT IDENTIFIERS ===
            "event_index": index,
            "payment_id": attempt.payment_id,
            "order_id": attempt.order_id,
            "session_id": attempt.session_id,

            # === OBSERVABLE FEATURES (model input) ===
            "amount_inr": attempt.amount_inr,
            "amount_bucket": self._bucket_amount(attempt.amount_inr),
            "method": attempt.method.value,
            "instrument": attempt.instrument,
            "error_code": attempt.error_code,
            "error_source": attempt.error_source.value,
            "attempt_number": attempt.attempt_number + event.prior_attempts_this_session,
            "hour_of_day": round(hour_of_day, 1),
            "is_evening": 17 <= hour_of_day <= 23,
            "is_weekend": False,  # Could be derived from timestamp
            "is_gateway_down": event.is_gateway_down,
            "is_bank_down": event.is_bank_down,
            "downtime_severity": round(event.downtime_severity, 3),
            "prior_attempts_this_session": event.prior_attempts_this_session,
            "time_since_session_start_seconds": round(
                event.time_since_session_start_seconds, 1
            ),
            "session_time_remaining_seconds": max(
                0.0,
                15 * 60 - event.time_since_session_start_seconds,
            ),

            # === LOGGED ACTION + PROPENSITY (for off-policy eval) ===
            "action": action.value,
            "propensity": round(propensity, 6),
            "action_cost": self._compute_action_cost(action),

            # === OUTCOME ===
            "recovered": outcome["recovered"],
            "recovered_amount": outcome["recovered_amount"],
            "was_self_cure": outcome["was_self_cure"],
            "intervention_cost": outcome["intervention_cost"],
            "net_value": outcome["net_value"],
            "time_to_outcome_seconds": round(outcome["time_to_outcome"], 1),

            # === LATENT GROUND TRUTH (for analysis only, NEVER model input) ===
            "_latent_self_cure_prob": round(self_cure_prob, 4),
            "_latent_p_recover": round(outcome["p_recover"], 4),
            "_latent_self_cure_propensity": round(
                event.customer.self_cure_propensity, 4
            ),
            "_latent_nudge_responsiveness": round(
                event.customer.nudge_responsiveness, 4
            ),
            "_latent_purchase_intent": round(event.customer.purchase_intent, 4),
        }

        # Add latent treatment effects for each action
        for a in RecoveryAction:
            record[f"_latent_tau_{a.value}"] = round(
                treatment_effects.get(a.value, 0.0), 4
            )

        return record

    @staticmethod
    def _bucket_amount(amount: float) -> str:
        """Bucket transaction amount into interpretable ranges."""
        if amount < 100:
            return "micro"
        elif amount < 500:
            return "small"
        elif amount < 2000:
            return "medium"
        elif amount < 10000:
            return "large"
        else:
            return "high_value"


def generate_batch(
    n_events: int = 10_000,
    seed: int = 42,
    epsilon: float = 0.1,
    merchant_policy: Optional[MerchantPolicy] = None,
    contribution_margin: float = 1.0,
) -> pd.DataFrame:
    """
    Convenience function to generate a synthetic batch.

    Args:
        n_events: Number of failure events to generate.
        seed: Random seed for reproducibility.
        epsilon: Epsilon-greedy exploration rate for the logging policy.
        merchant_policy: Optional merchant policy constraints.
        contribution_margin: Merchant contribution margin fraction ∈ (0, 1].

    Returns:
        DataFrame with observable features, logged actions, outcomes,
        and latent ground truth (prefixed with _latent_).
    """
    generator = SyntheticDataGenerator(
        n_events=n_events,
        seed=seed,
        epsilon=epsilon,
        merchant_policy=merchant_policy,
        contribution_margin=contribution_margin,
    )
    return generator.generate_batch()
