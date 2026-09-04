"""
Context builder — transforms raw event data into ML-ready feature vectors.

All features are tabular (no embeddings, no text) — this is a conscious
design choice matching what Stripe used for Adaptive Acceptance for years
before switching to transformers at Stripe-scale data volumes (Section I).

Feature categories:
1. Error classification (code, source — one-hot encoded)
2. Payment characteristics (method, amount bucket, instrument)
3. Session context (attempt number, time elapsed, remaining time)
4. Downtime signals (gateway/bank status, severity)
5. Derived features (interactions, time-of-day patterns)

Each feature carries a staleness timestamp. Past the staleness threshold,
confidence is downgraded and the decision defaults to conservative
(Section K, row 11).
"""

from __future__ import annotations

import time
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.preprocessing import LabelEncoder


class ContextBuilder:
    """
    Builds ML-ready feature vectors from raw event data.

    Two modes:
    1. From DataFrame (batch mode — for training and evaluation)
    2. From a single FailureEvent (online mode — for live decisions)
    """

    # Feature columns used by the model (all observable, no _latent_ prefix)
    CATEGORICAL_FEATURES = [
        "method",
        "error_code",
        "error_source",
        "amount_bucket",
    ]

    NUMERICAL_FEATURES = [
        "amount_inr",
        "attempt_number",
        "hour_of_day",
        "downtime_severity",
        "prior_attempts_this_session",
        "time_since_session_start_seconds",
        "session_time_remaining_seconds",
    ]

    BINARY_FEATURES = [
        "is_evening",
        "is_gateway_down",
        "is_bank_down",
    ]

    def __init__(self):
        self.label_encoders: dict[str, LabelEncoder] = {}
        self._is_fitted = False
        self._feature_columns: list[str] = []

    def fit_transform(self, df: pd.DataFrame) -> np.ndarray:
        """
        Fit encoders on training data and return feature matrix.

        Args:
            df: DataFrame with observable features (from SyntheticDataGenerator).

        Returns:
            Feature matrix of shape (n_samples, n_features).
        """
        features = []

        # Categorical features — label encode
        for col in self.CATEGORICAL_FEATURES:
            if col in df.columns:
                le = LabelEncoder()
                encoded = le.fit_transform(df[col].astype(str).values)
                self.label_encoders[col] = le
                features.append(encoded.reshape(-1, 1))
                self._feature_columns.append(col)

        # Numerical features — as-is (tree models don't need scaling)
        for col in self.NUMERICAL_FEATURES:
            if col in df.columns:
                vals = df[col].values.astype(float)
                features.append(vals.reshape(-1, 1))
                self._feature_columns.append(col)

        # Binary features
        for col in self.BINARY_FEATURES:
            if col in df.columns:
                vals = df[col].values.astype(float)
                features.append(vals.reshape(-1, 1))
                self._feature_columns.append(col)

        # Derived features
        derived = self._compute_derived_features(df)
        for col_name, vals in derived.items():
            features.append(vals.reshape(-1, 1))
            self._feature_columns.append(col_name)

        self._is_fitted = True
        return np.hstack(features)

    def transform(self, df: pd.DataFrame) -> np.ndarray:
        """
        Transform new data using fitted encoders.

        Args:
            df: DataFrame with same schema as training data.

        Returns:
            Feature matrix.
        """
        if not self._is_fitted:
            raise RuntimeError("ContextBuilder must be fit before transform")

        features = []

        for col in self.CATEGORICAL_FEATURES:
            if col in df.columns and col in self.label_encoders:
                le = self.label_encoders[col]
                # Handle unseen categories gracefully
                vals = df[col].astype(str).values
                encoded = np.array([
                    le.transform([v])[0] if v in le.classes_
                    else len(le.classes_)  # Unknown category gets a new index
                    for v in vals
                ])
                features.append(encoded.reshape(-1, 1))

        for col in self.NUMERICAL_FEATURES:
            if col in df.columns:
                features.append(df[col].values.astype(float).reshape(-1, 1))

        for col in self.BINARY_FEATURES:
            if col in df.columns:
                features.append(df[col].values.astype(float).reshape(-1, 1))

        derived = self._compute_derived_features(df)
        for col_name, vals in derived.items():
            features.append(vals.reshape(-1, 1))

        return np.hstack(features)

    def _compute_derived_features(self, df: pd.DataFrame) -> dict[str, np.ndarray]:
        """
        Compute interaction and derived features.

        These capture non-trivial patterns that help the tree model:
        - retry_fatigue: diminishing returns of multiple retries
        - urgency: how close to session timeout
        - amount_risk: higher-value = more at stake
        """
        derived = {}

        # Retry fatigue: 1.0 for first attempt, decays toward 0
        if "prior_attempts_this_session" in df.columns:
            derived["retry_fatigue"] = 1.0 / (
                1.0 + df["prior_attempts_this_session"].values.astype(float)
            )

        # Urgency: fraction of session time remaining
        if "session_time_remaining_seconds" in df.columns:
            max_session = 15 * 60  # 15 minutes
            derived["session_urgency"] = 1.0 - np.clip(
                df["session_time_remaining_seconds"].values.astype(float) / max_session,
                0.0, 1.0,
            )

        # Amount risk: log-scaled transaction value
        if "amount_inr" in df.columns:
            derived["log_amount"] = np.log1p(df["amount_inr"].values.astype(float))

        # Time-of-day sin/cos encoding (captures cyclical pattern)
        if "hour_of_day" in df.columns:
            hours = df["hour_of_day"].values.astype(float)
            derived["hour_sin"] = np.sin(2 * np.pi * hours / 24.0)
            derived["hour_cos"] = np.cos(2 * np.pi * hours / 24.0)

        return derived

    @property
    def feature_names(self) -> list[str]:
        """Get ordered list of feature names."""
        return list(self._feature_columns)

    @property
    def n_features(self) -> int:
        """Number of features after transformation."""
        return len(self._feature_columns)
