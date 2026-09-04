"""
CATE / Uplift Estimators for PaymentPulse.

Target Definition (Section 4 Audit):
-----------------------------------
The models estimate Conditional Average Treatment Effect on Recovery Probability:
    τ_P(x, a) = P(recovered=1 | X=x, do(A=a)) − P(recovered=1 | X=x, do(A=do_nothing))

Properties:
- Dimensionless: τ̂_P(x, a) ∈ [-1.0, 1.0].
- Reference arm is strictly DO_NOTHING (control): τ̂_P(x, do_nothing) ≡ 0.0.
- Directly measures incremental lift over natural self-cure.
- Scaled by GMV, contribution margin, and action cost in ActionRanker.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

from rally.domain.enums import RecoveryAction

logger = logging.getLogger(__name__)


class TLearnerUpliftModel:
    """
    T-Learner: fits a separate outcome model μ̂_a(x) per treatment arm.
    Predicted uplift: τ̂_P(x, a) = μ̂_a(x) − μ̂_control(x).

    This is the DEPLOYABLE PaymentPulse model. It learns exclusively from 
    pre-decision observable context and historically logged outcomes.

    Causal Assumptions Required for Valid Estimation:
    1. Unconfoundedness (No unmeasured confounders between action and outcome).
    2. Overlap / Positivity (Every context has >0 probability of receiving any action).
    3. SUTVA (No interference between independent payment events).

    *Note: This estimator is NOT inherently unbiased; it relies entirely on the 
    quality and support of the logged dataset and correct model specification.*
    """

    def __init__(
        self,
        max_depth: int = 5,
        n_estimators: int = 150,
        learning_rate: float = 0.05,
        min_samples_leaf: int = 20,
        random_state: int = 42,
    ):
        self.model_params = {
            "max_depth": max_depth,
            "max_iter": n_estimators,
            "learning_rate": learning_rate,
            "min_samples_leaf": min_samples_leaf,
            "random_state": random_state,
        }
        self.models: dict[str, HistGradientBoostingRegressor] = {}
        self._is_fitted = False
        self._actions: list[str] = []

    def fit(
        self,
        X: np.ndarray,
        actions: np.ndarray,
        outcomes: np.ndarray,
        propensities: Optional[np.ndarray] = None,
    ) -> TLearnerUpliftModel:
        if np.any(outcomes < 0.0) or np.any(outcomes > 1.0):
            raise ValueError(
                "TLearner target must be binary recovery indicators or probabilities in [0.0, 1.0]. "
                "Passing INR values directly causes a unit mismatch with ActionRanker."
            )

        self._actions = sorted(set(actions))

        for action_label in self._actions:
            mask = actions == action_label
            X_arm = X[mask]
            y_arm = outcomes[mask]

            if len(X_arm) < 10:
                logger.warning(f"Too few samples for action arm '{action_label}' ({len(X_arm)}). Skipping model.")
                continue

            if "categorical_features" not in self.model_params:
                self.model_params["categorical_features"] = [0, 1, 2, 3]

            model = HistGradientBoostingRegressor(**self.model_params)
            model.fit(X_arm, y_arm)
            self.models[action_label] = model

        self._is_fitted = True
        return self

    def predict_uplift(self, X: np.ndarray, action: str) -> np.ndarray:
        if not self._is_fitted:
            raise RuntimeError("Model must be fitted before prediction.")

        control_key = RecoveryAction.DO_NOTHING.value
        if action == control_key:
            return np.zeros(len(X), dtype=float)

        if control_key in self.models:
            mu_control = np.clip(self.models[control_key].predict(X), 0.0, 1.0)
        else:
            mu_control = np.zeros(len(X), dtype=float)

        if action in self.models:
            mu_treatment = np.clip(self.models[action].predict(X), 0.0, 1.0)
        else:
            mu_treatment = mu_control.copy()

        uplift = mu_treatment - mu_control
        return np.clip(uplift, -1.0, 1.0)

    def predict_all_uplifts(self, X: np.ndarray) -> dict[str, np.ndarray]:
        uplifts: dict[str, np.ndarray] = {}
        for action in RecoveryAction:
            if action == RecoveryAction.DO_NOTHING:
                uplifts[action.value] = np.zeros(len(X), dtype=float)
            else:
                uplifts[action.value] = self.predict_uplift(X, action.value)
        return uplifts


class SLearnerUpliftModel:
    """
    S-Learner: fits a single outcome model μ̂(x, a) across all actions.
    Predicted uplift: τ̂_P(x, a) = μ̂(x, a) − μ̂(x, do_nothing).
    """

    def __init__(
        self,
        max_depth: int = 6,
        n_estimators: int = 200,
        learning_rate: float = 0.05,
        min_samples_leaf: int = 20,
        random_state: int = 42,
    ):
        self.model_params = {
            "max_depth": max_depth,
            "max_iter": n_estimators,
            "learning_rate": learning_rate,
            "min_samples_leaf": min_samples_leaf,
            "random_state": random_state,
        }
        self.model: Optional[HistGradientBoostingRegressor] = None
        self._is_fitted = False
        self._action_encoder: dict[str, int] = {}
        self._actions: list[str] = []

    def fit(
        self,
        X: np.ndarray,
        actions: np.ndarray,
        outcomes: np.ndarray,
        propensities: Optional[np.ndarray] = None,
    ) -> SLearnerUpliftModel:
        self._actions = sorted(set(actions))
        self._action_encoder = {a: i for i, a in enumerate(self._actions)}

        actions_encoded = np.array([self._action_encoder[a] for a in actions])
        X_augmented = np.column_stack([X, actions_encoded])

        if "categorical_features" not in self.model_params:
            self.model_params["categorical_features"] = [0, 1, 2, 3, X_augmented.shape[1] - 1]

        self.model = HistGradientBoostingRegressor(**self.model_params)
        
        # Do not use IPW for tree models with binary targets as it severely increases variance
        # and overfits the rare actions.
        self.model.fit(X_augmented, outcomes)
            
        self._is_fitted = True
        return self

    def predict_uplift(self, X: np.ndarray, action: str) -> np.ndarray:
        if not self._is_fitted or self.model is None:
            raise RuntimeError("Model must be fitted before prediction.")

        control_key = RecoveryAction.DO_NOTHING.value
        if action == control_key:
            return np.zeros(len(X), dtype=float)

        control_idx = self._action_encoder.get(control_key, 0)
        action_idx = self._action_encoder.get(action, control_idx)

        X_control = np.column_stack([X, np.full(len(X), control_idx)])
        mu_control = np.clip(self.model.predict(X_control), 0.0, 1.0)

        X_treat = np.column_stack([X, np.full(len(X), action_idx)])
        mu_treatment = np.clip(self.model.predict(X_treat), 0.0, 1.0)

        return np.clip(mu_treatment - mu_control, -1.0, 1.0)

    def predict_all_uplifts(self, X: np.ndarray) -> dict[str, np.ndarray]:
        uplifts: dict[str, np.ndarray] = {}
        for action in RecoveryAction:
            if action == RecoveryAction.DO_NOTHING:
                uplifts[action.value] = np.zeros(len(X), dtype=float)
            else:
                uplifts[action.value] = self.predict_uplift(X, action.value)
        return uplifts


class OraclePolicyModel:
    """
    [DIAGNOSTIC ORACLE ONLY — NON-DEPLOYABLE]
    
    Oracle Policy Learner — predicts the optimal action directly as a
    classification problem, bypassing uplift estimation entirely.

    This model is trained strictly on latent counterfactual potential outcomes
    (simulator ground truth) that are unobservable in the real world prior to
    a decision. 
    
    It must NEVER be presented as the deployable PaymentPulse model. It exists
    solely to establish the theoretical maximum ceiling (Oracle bounds) of what
    could be achieved if the model perfectly mapped the observable context to the
    true underlying potential outcomes.
    """

    def __init__(
        self,
        max_depth: int = 6,
        n_estimators: int = 200,
        learning_rate: float = 0.05,
        min_samples_leaf: int = 20,
        random_state: int = 42,
    ):
        from sklearn.ensemble import HistGradientBoostingClassifier
        self.model_params = {
            "max_depth": max_depth,
            "max_iter": n_estimators,
            "learning_rate": learning_rate,
            "min_samples_leaf": min_samples_leaf,
            "random_state": random_state,
            "categorical_features": [0, 1, 2, 3],
        }
        self.clf: Optional[HistGradientBoostingClassifier] = None
        self._is_fitted = False
        self._label_map: dict[str, int] = {}
        self._reverse_map: dict[int, str] = {}

    def fit(
        self,
        X: np.ndarray,
        oracle_actions: np.ndarray,
    ) -> OraclePolicyModel:
        """
        Train on oracle action labels.

        Args:
            X: Observable feature matrix (n_samples, n_features).
            oracle_actions: Ground-truth optimal action labels (n_samples,).
        """
        from sklearn.ensemble import HistGradientBoostingClassifier

        action_values = sorted(set(oracle_actions))
        self._label_map = {a: i for i, a in enumerate(action_values)}
        self._reverse_map = {i: a for a, i in self._label_map.items()}

        y = np.array([self._label_map[a] for a in oracle_actions])

        self.clf = HistGradientBoostingClassifier(**self.model_params)
        self.clf.fit(X, y)

        self._is_fitted = True
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict the best action for each sample."""
        if not self._is_fitted or self.clf is None:
            raise RuntimeError("Model must be fitted before prediction.")

        y_pred = self.clf.predict(X)
        return np.array([self._reverse_map[y] for y in y_pred])

    def predict_proba(self, X: np.ndarray) -> dict[str, np.ndarray]:
        """Predict action probabilities for each sample."""
        if not self._is_fitted or self.clf is None:
            raise RuntimeError("Model must be fitted before prediction.")

        proba = self.clf.predict_proba(X)
        result = {}
        for i, action_val in self._reverse_map.items():
            if i < proba.shape[1]:
                result[action_val] = proba[:, i]
            else:
                result[action_val] = np.zeros(len(X))
        return result

    def predict_all_uplifts(self, X: np.ndarray) -> dict[str, np.ndarray]:
        """
        Compatibility shim: convert class probabilities to pseudo-uplift scores.

        The OraclePolicyModel doesn't estimate uplift directly. Instead, it returns the
        known deterministic simulator ground truth value minus intervention cost.
        
        This ensures the Oracle works with the existing pipeline
        without requiring a separate model interface.
        """
        proba = self.predict_proba(X)
        uplifts: dict[str, np.ndarray] = {}
        for action in RecoveryAction:
            if action == RecoveryAction.DO_NOTHING:
                uplifts[action.value] = np.zeros(len(X), dtype=float)
            elif action.value in proba:
                # Scale probabilities to uplift-like range [0, 0.3]
                # to be compatible with ActionRanker's unit expectations
                uplifts[action.value] = proba[action.value] * 0.3
            else:
                uplifts[action.value] = np.zeros(len(X), dtype=float)
        return uplifts

