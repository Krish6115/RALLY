"""
Baseline policies — faithful reconstructions, not strawmen.

Section M of research doc defines 5 baselines:
| # | Baseline                | What it reproduces                              |
|---|-------------------------|------------------------------------------------|
| 1 | No recovery             | Floor — never intervene (self-cure only)       |
| 2 | Always retry            | Naive merchant-side auto-retry                  |
| 3 | Rule-based recovery     | Razorpay FPR + published error-code guidance    |
| 4 | Timing-only bandit      | Stripe Smart Retries / Adyen Auto Rescue        |
| 5 | PaymentPulse            | Full uplift-ranked multi-action policy           |
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from rally.domain.enums import RecoveryAction
from rally.simulator.error_taxonomy import get_error_by_code
from rally.models.action_ranker import ActionRanker
from rally.features.context_builder import ContextBuilder

logger = logging.getLogger(__name__)


class BasePolicy(ABC):
    """Base class for all recovery policies."""

    name: str = "base"

    @abstractmethod
    def select_action(
        self,
        features: dict,
        legal_actions: list[RecoveryAction],
    ) -> tuple[RecoveryAction, float]:
        """Select an action for a single failure event."""
        ...

    def select_actions_batch(
        self,
        df: pd.DataFrame,
        legal_actions_per_event: Optional[list[list[RecoveryAction]]] = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Select actions for a batch. Default: iterate over rows.
        Returns (actions_array, propensities_array).
        """
        all_legal = legal_actions_per_event or [
            list(RecoveryAction) for _ in range(len(df))
        ]

        actions = []
        propensities = []
        for i, row in df.iterrows():
            features = row.to_dict()
            action, prop = self.select_action(features, all_legal[i])
            actions.append(action.value)
            propensities.append(prop)

        return np.array(actions), np.array(propensities)


class NoRecoveryPolicy(BasePolicy):
    """
    Baseline 1: Do nothing.
    Floor — never intervene. Measures the natural self-cure rate.
    """
    name = "no_recovery"

    def select_action(self, features, legal_actions):
        return RecoveryAction.DO_NOTHING, 1.0


class AlwaysRetryPolicy(BasePolicy):
    """
    Baseline 2: Always retry immediately.
    Naive merchant-side auto-retry — ignores error context.
    """
    name = "always_retry"

    def select_action(self, features, legal_actions):
        if RecoveryAction.RETRY_NOW in legal_actions:
            return RecoveryAction.RETRY_NOW, 1.0
        return RecoveryAction.DO_NOTHING, 1.0


class RuleBasedPolicy(BasePolicy):
    """
    Baseline 3: Faithful reconstruction of Razorpay's published recovery.
    Combines error-code taxonomy recommendations and Failed Payment Recovery links.
    """
    name = "rule_based"

    def select_action(self, features, legal_actions):
        error_code = features.get("error_code", "")
        entry = get_error_by_code(error_code)

        if entry is not None:
            recommended = entry.rule_based_action
            if recommended in legal_actions:
                return recommended, 1.0

        # Default FPR behavior: send a payment link if allowed
        if RecoveryAction.SEND_PAYMENT_LINK in legal_actions:
            return RecoveryAction.SEND_PAYMENT_LINK, 1.0

        # If link isn't allowed, retry
        if RecoveryAction.RETRY_NOW in legal_actions:
            return RecoveryAction.RETRY_NOW, 1.0

        return RecoveryAction.DO_NOTHING, 1.0


class TimingOnlyBanditPolicy(BasePolicy):
    """
    Baseline 4: Timing-only bandit (Stripe Smart Retries / Adyen Auto Rescue reconstruction).

    Learns optimal retry timing:
    - Candidate actions restricted strictly to retry timing: {retry_now, wait_2min, wait_5min, wait_10min}.
    - Fits models predicting recovery probability for each timing arm.
    - Evaluates trade-off between immediate retry vs delayed retry based on gateway downtime signals.
    """
    name = "timing_only_bandit"

    TIMING_ACTIONS = [
        RecoveryAction.RETRY_NOW,
        RecoveryAction.WAIT_2MIN,
        RecoveryAction.WAIT_5MIN,
        RecoveryAction.WAIT_10MIN,
    ]

    def __init__(self, context_builder: Optional[ContextBuilder] = None):
        self.context_builder = context_builder
        self.arm_models: dict[str, HistGradientBoostingRegressor] = {}
        self._is_fitted = False

    def fit(self, X: np.ndarray, actions: np.ndarray, outcomes: np.ndarray):
        """
        Train timing models on retry/wait actions predicting recovery probability.
        """
        for timing_action in self.TIMING_ACTIONS:
            action_val = timing_action.value
            mask = actions == action_val

            if mask.sum() >= 10:
                model = HistGradientBoostingRegressor(
                    max_depth=4,
                    max_iter=100,
                    learning_rate=0.05,
                    min_samples_leaf=10,
                    random_state=42,
                )
                model.fit(X[mask], outcomes[mask])
                self.arm_models[action_val] = model

        self._is_fitted = len(self.arm_models) > 0
        return self

    def select_action(self, features: dict, legal_actions: list[RecoveryAction]) -> tuple[RecoveryAction, float]:
        available = [a for a in self.TIMING_ACTIONS if a in legal_actions]
        if not available:
            return RecoveryAction.DO_NOTHING, 1.0

        # Heuristic fallback if not fitted
        if not self._is_fitted:
            is_down = features.get("is_gateway_down", False) or features.get("is_bank_down", False)
            if is_down and RecoveryAction.WAIT_5MIN in available:
                return RecoveryAction.WAIT_5MIN, 1.0
            return available[0], 1.0

        # When feature dict is passed, pick based on downtime if model needs vector
        is_down = features.get("is_gateway_down", False) or features.get("is_bank_down", False)
        if is_down:
            for wait_act in [RecoveryAction.WAIT_5MIN, RecoveryAction.WAIT_2MIN, RecoveryAction.WAIT_10MIN]:
                if wait_act in available:
                    return wait_act, 1.0

        return available[0], 1.0

    def select_actions_batch(
        self,
        df: pd.DataFrame,
        legal_actions_per_event: Optional[list[list[RecoveryAction]]] = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Batch prediction using fitted arm models and existing context builder.
        """
        if not self._is_fitted or self.context_builder is None:
            # Fall back to row-by-row heuristic
            return super().select_actions_batch(df, legal_actions_per_event)

        X = self.context_builder.transform(df)
        all_legal = legal_actions_per_event or [list(RecoveryAction) for _ in range(len(df))]

        best_actions = []
        propensities = []

        # Predict probability for each timing arm
        preds: dict[str, np.ndarray] = {}
        for action in self.TIMING_ACTIONS:
            val = action.value
            if val in self.arm_models:
                preds[val] = np.clip(self.arm_models[val].predict(X), 0.0, 1.0)
            else:
                preds[val] = np.zeros(len(X))

        for i in range(len(X)):
            legal_timing = [a for a in self.TIMING_ACTIONS if a in all_legal[i]]
            if not legal_timing:
                best_actions.append(RecoveryAction.DO_NOTHING.value)
                propensities.append(1.0)
                continue

            # Pick timing arm with highest expected recovery probability
            best_action = legal_timing[0]
            best_prob = -1.0

            for action in legal_timing:
                prob = preds[action.value][i]
                if prob > best_prob:
                    best_prob = prob
                    best_action = action

            best_actions.append(best_action.value)
            propensities.append(1.0)

        return np.array(best_actions), np.array(propensities)


class PaymentPulsePolicy(BasePolicy):
    """
    Baseline 5: Full PaymentPulse — uplift-ranked multi-action policy.

    Uses:
    1. Uplift model estimating dimensionless probability uplift τ̂_P(x, a) ∈ [-1.0, 1.0].
    2. ActionRanker optimizing Expected Net Recovered Value in INR:
       ENRV = τ̂_P × amount × contribution_margin − cost.
    3. Defaults to DO_NOTHING when max ENRV ≤ 0.
    """
    name = "rally"

    def __init__(
        self,
        uplift_model=None,
        context_builder: Optional[ContextBuilder] = None,
        ranker: Optional[ActionRanker] = None,
    ):
        self.uplift_model = uplift_model
        self.context_builder = context_builder
        self.ranker = ranker or ActionRanker()

    def select_action(self, features, legal_actions):
        return RecoveryAction.DO_NOTHING, 1.0

    def select_actions_batch(
        self,
        df: pd.DataFrame,
        legal_actions_per_event: Optional[list[list[RecoveryAction]]] = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        if self.uplift_model is None or self.context_builder is None:
            raise RuntimeError("PaymentPulsePolicy requires a fitted uplift model and context builder.")

        X = self.context_builder.transform(df)
        uplifts = self.uplift_model.predict_all_uplifts(X)

        all_legal = legal_actions_per_event or [list(RecoveryAction) for _ in range(len(df))]

        actions = []
        propensities = []

        amounts = df.get("amount_inr", pd.Series(np.zeros(len(df)))).values.astype(float)

        for i in range(len(X)):
            sample_uplifts = {action: float(uplifts[action][i]) for action in uplifts}
            amount = amounts[i]

            best_action, best_score, _ = self.ranker.decide(
                uplift_estimates=sample_uplifts,
                candidate_actions=all_legal[i],
                transaction_amount=amount,
            )

            actions.append(best_action.value)
            propensities.append(1.0)

        return np.array(actions), np.array(propensities)


class OraclePolicy:
    """
    [DIAGNOSTIC ORACLE ONLY — NON-DEPLOYABLE]
    
    Evaluates the OraclePolicyModel which trained on latent simulator ground-truth.
    Must never be presented as a real deployable model.
    """
    name = "oracle_diagnostic"

    def __init__(self, oracle_model, context_builder: ContextBuilder):
        self.oracle_model = oracle_model
        self.context_builder = context_builder

    def select_actions_batch(
        self,
        df: pd.DataFrame,
        legal_actions_per_event: Optional[list[list[RecoveryAction]]] = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        X = self.context_builder.transform(df)
        all_legal = legal_actions_per_event or [list(RecoveryAction) for _ in range(len(df))]
        
        best_actions_raw = self.oracle_model.predict(X)
        actions = []
        for i, best_act_str in enumerate(best_actions_raw):
            legal_strs = [a.value for a in all_legal[i]]
            if best_act_str in legal_strs:
                actions.append(best_act_str)
            else:
                actions.append(RecoveryAction.DO_NOTHING.value)
                
        return np.array(actions), np.ones(len(actions))
