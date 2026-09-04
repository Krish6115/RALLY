"""
Doubly Robust (DR) off-policy evaluation.

Mathematical Formulation (Section 4 Audit):
--------------------------------------------
Given logged bandit feedback (x_i, a_i, p_i, r_i), for a target policy π choosing a*_i:
1. Direct Method (DM):
       V_DM(i) = μ̂(x_i, a*_i)
2. Inverse Propensity Scoring (IPS):
       V_IPS(i) = (I(a_i == a*_i) / p_i) × r_i
3. Doubly Robust (DR):
       V_DR(i) = μ̂(x_i, a*_i) + (I(a_i == a*_i) / p_i) × (r_i − μ̂(x_i, a_i))

Properties:
- Unbiased if EITHER the propensity p_i is correct OR the reward model μ̂ is correct.
- Propensities are validated strictly: p_i ∈ (0.0, 1.0].
- Propensities are clipped to min_propensity to prevent unbounded variance.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from rally.domain.enums import RecoveryAction
from rally.features.context_builder import ContextBuilder

logger = logging.getLogger(__name__)


def compute_doubly_robust_scores(
    target_actions: np.ndarray,
    logged_actions: np.ndarray,
    logged_propensities: np.ndarray,
    logged_rewards: np.ndarray,
    mu_target: np.ndarray,
    mu_logged: np.ndarray,
    min_propensity: float = 0.01,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Pure mathematical computation of DR, IPS, and DM scores.

    Returns:
        (dr_scores, ips_scores, dm_scores)
    """
    target_actions = np.asarray(target_actions)
    logged_actions = np.asarray(logged_actions)
    logged_propensities = np.asarray(logged_propensities, dtype=float)
    logged_rewards = np.asarray(logged_rewards, dtype=float)
    mu_target = np.asarray(mu_target, dtype=float)
    mu_logged = np.asarray(mu_logged, dtype=float)

    n = len(logged_actions)
    if not (len(target_actions) == n == len(logged_propensities) == len(logged_rewards) == len(mu_target) == len(mu_logged)):
        raise ValueError("All input arrays must have identical length.")

    # Validate propensities
    if np.any(logged_propensities <= 0.0):
        raise ValueError("Logging propensities must be strictly positive (p > 0). Found values ≤ 0.")
    if np.any(logged_propensities > 1.0001):
        raise ValueError("Logging propensities cannot exceed 1.0. Found values > 1.")

    p_clipped = np.clip(logged_propensities, min_propensity, 1.0)
    indicator = (target_actions == logged_actions).astype(float)
    weights = indicator / p_clipped

    dm_scores = mu_target
    ips_scores = weights * logged_rewards
    dr_scores = mu_target + weights * (logged_rewards - mu_logged)

    return dr_scores, ips_scores, dm_scores


class DoublyRobustEstimator:
    """
    Trains reward model μ̂(x, a) on training data, and evaluates target policies
    on test cohorts using Doubly Robust off-policy estimation.
    """

    def __init__(self, df_train: pd.DataFrame, context_builder: Optional[ContextBuilder] = None):
        self.context_builder = context_builder or ContextBuilder()
        self.reward_models: dict[str, HistGradientBoostingRegressor] = {}
        self.action_classes: list[str] = []
        self._fit_reward_model(df_train)

    def _fit_reward_model(self, df_train: pd.DataFrame):
        """Train μ̂(x, a) predicting net_value on training data using T-Learner approach."""
        X = self.context_builder.fit_transform(df_train)
        logged_actions = df_train["action"].values
        outcomes = df_train["net_value"].values.astype(float)

        self.action_classes = sorted(set(logged_actions))

        for action in self.action_classes:
            mask = logged_actions == action
            if mask.sum() < 10:
                continue
            
            X_arm = X[mask]
            y_arm = outcomes[mask]
            
            model = HistGradientBoostingRegressor(
                max_depth=5,
                max_iter=150,
                learning_rate=0.05,
                random_state=42,
            )
            model.fit(X_arm, y_arm)
            self.reward_models[action] = model

    def predict_reward(self, X: np.ndarray, actions: np.ndarray) -> np.ndarray:
        """Predict expected reward μ̂(x, a) for given feature matrix and actions."""
        if not self.reward_models:
            raise RuntimeError("Reward models must be fitted first.")

        predictions = np.zeros(len(X))
        for action, model in self.reward_models.items():
            mask = actions == action
            if mask.any():
                predictions[mask] = model.predict(X[mask])
        
        return predictions

    def evaluate_policy(
        self,
        df_eval: pd.DataFrame,
        target_actions: np.ndarray,
        min_propensity: float = 0.01,
    ) -> dict[str, np.ndarray]:
        """
        Evaluate a target policy on an out-of-sample evaluation dataset.

        Returns dict with:
        - "dr_scores": np.ndarray
        - "ips_scores": np.ndarray
        - "dm_scores": np.ndarray
        """
        X_eval = self.context_builder.transform(df_eval)
        logged_actions = df_eval["action"].values
        logged_propensities = df_eval["propensity"].values.astype(float)
        logged_rewards = df_eval["net_value"].values.astype(float)

        mu_target = self.predict_reward(X_eval, target_actions)
        mu_logged = self.predict_reward(X_eval, logged_actions)

        dr, ips, dm = compute_doubly_robust_scores(
            target_actions=target_actions,
            logged_actions=logged_actions,
            logged_propensities=logged_propensities,
            logged_rewards=logged_rewards,
            mu_target=mu_target,
            mu_logged=mu_logged,
            min_propensity=min_propensity,
        )

        return {
            "dr_scores": dr,
            "ips_scores": ips,
            "dm_scores": dm,
        }
