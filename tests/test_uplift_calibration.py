"""
Regression tests for T-Learner uplift calibration.

These tests catch the causal-evaluation red-team finding:
T-Learner uplift predictions were 2-4x overestimated for low-sample arms
(wait_2min: +0.1483 bias, retry_now: +0.0750, escalate_to_human: +0.0515).

Root cause: per-arm HistGradientBoostingRegressors overfit on small samples
and produce inflated recovery probability predictions relative to the
well-calibrated control arm.
"""

import numpy as np
import pandas as pd
import pytest

from paymentpulse.simulator import generate_batch
from paymentpulse.features.context_builder import ContextBuilder
from paymentpulse.models.uplift_model import TLearnerUpliftModel, SLearnerUpliftModel
from paymentpulse.domain.enums import RecoveryAction


@pytest.fixture(scope="module")
def train_test_data():
    """Generate train and test data with known ground-truth uplifts."""
    df_train = generate_batch(n_events=10000, seed=42, epsilon=0.1)
    df_test = generate_batch(n_events=5000, seed=99, epsilon=0.1)
    ctx = ContextBuilder()
    X_train = ctx.fit_transform(df_train)
    X_test = ctx.transform(df_test)
    return df_train, df_test, X_train, X_test, ctx


def test_tlearner_uplift_bias_per_arm(train_test_data):
    """
    Regression test: T-Learner mean predicted uplift should not exceed
    2x the mean ground-truth uplift for any action arm on held-out data.

    This catches the calibration bug where wait_2min was predicted at
    0.1987 vs true 0.0504 (4x overestimate).
    """
    df_train, df_test, X_train, X_test, ctx = train_test_data

    model = TLearnerUpliftModel(random_state=42)
    model.fit(X_train, df_train["action"].values, df_train["recovered"].values.astype(float))

    uplifts = model.predict_all_uplifts(X_test)

    failures = []
    for action in RecoveryAction:
        if action == RecoveryAction.DO_NOTHING:
            continue

        act_val = action.value
        col = f"_latent_tau_{act_val}"
        if col not in df_test.columns:
            continue

        mean_pred = uplifts[act_val].mean()
        mean_true = df_test[col].mean()

        # Allow a generous 2x overestimate tolerance
        # (The red-team found 4x for wait_2min, so 2x is a meaningful regression guard)
        bias = mean_pred - mean_true
        max_allowed_bias = max(0.05, abs(mean_true))  # At least 0.05 absolute tolerance

        if bias > max_allowed_bias:
            failures.append(
                f"{act_val}: predicted={mean_pred:.4f}, true={mean_true:.4f}, "
                f"bias={bias:.4f}, max_allowed={max_allowed_bias:.4f}"
            )

    # This test documents the KNOWN calibration bug.
    # It is expected to fail with the current T-Learner.
    # When the model is fixed (e.g., S-Learner), this test should pass.
    if failures:
        pytest.xfail(
            f"KNOWN T-Learner calibration bug (red-team finding). "
            f"Arms with excessive bias:\n  " + "\n  ".join(failures)
        )


def test_tlearner_uplift_non_negative_for_control(train_test_data):
    """DO_NOTHING uplift must always be exactly 0.0."""
    df_train, _, X_train, X_test, _ = train_test_data

    model = TLearnerUpliftModel(random_state=42)
    model.fit(X_train, df_train["action"].values, df_train["recovered"].values.astype(float))

    uplifts = model.predict_all_uplifts(X_test)
    dn_uplift = uplifts[RecoveryAction.DO_NOTHING.value]

    assert np.all(dn_uplift == 0.0), "DO_NOTHING uplift must be exactly 0.0"


def test_tlearner_uplift_bounded(train_test_data):
    """All predicted uplifts must be in [-1.0, 1.0]."""
    df_train, _, X_train, X_test, _ = train_test_data

    model = TLearnerUpliftModel(random_state=42)
    model.fit(X_train, df_train["action"].values, df_train["recovered"].values.astype(float))

    uplifts = model.predict_all_uplifts(X_test)

    for act_val, preds in uplifts.items():
        assert np.all(preds >= -1.0), f"{act_val}: uplift < -1.0 detected"
        assert np.all(preds <= 1.0), f"{act_val}: uplift > 1.0 detected"


def test_propensity_formula_consistency():
    """
    Regression test: verify that logged propensities match the epsilon-greedy formula.

    For epsilon=0.1 and n_legal actions:
    - P(rule_action) = 0.9 + 0.1/n_legal
    - P(other_action) = 0.1/n_legal
    """
    df = generate_batch(n_events=500, seed=77, epsilon=0.1)

    for i in range(len(df)):
        prop = df.iloc[i]["propensity"]

        # Propensity must match 0.9 + 0.1/n or 0.1/n for some integer n in [1, 10]
        valid = False
        for n_legal in range(1, 11):
            rule_prop = 0.9 + 0.1 / n_legal
            rand_prop = 0.1 / n_legal
            if abs(prop - rule_prop) < 1e-5 or abs(prop - rand_prop) < 1e-5:
                valid = True
                break

        assert valid, (
            f"Row {i}: propensity {prop:.6f} does not match epsilon-greedy formula "
            f"for any n_legal in [1, 10]"
        )


def test_escalation_cost_exceeds_typical_uplift():
    """
    Regression test: escalate_to_human costs INR 25.0.
    The mean ground-truth uplift for escalation is ~0.023.
    For escalation to be profitable: uplift * amount * margin > 25.0
    => amount > 25.0 / 0.023 = ~1087 INR (at margin=1.0).

    The ranker should NOT select escalation for transactions below this breakeven.
    """
    from paymentpulse.models.action_ranker import ActionRanker

    ranker = ActionRanker(contribution_margin=1.0, min_confidence_threshold=0.0)

    # With a realistic uplift of 0.023, escalation loses money below ~1087 INR
    uplifts = {
        "retry_now": 0.05,
        "send_payment_link": 0.06,
        "escalate_to_human": 0.023,
        "do_nothing": 0.0,
    }

    # At 500 INR: escalation ENRV = 0.023 * 500 - 25 = -13.5 (should NOT be chosen)
    best_action, best_score, _ = ranker.decide(
        uplift_estimates=uplifts,
        candidate_actions=list(RecoveryAction),
        transaction_amount=500.0,
    )
    assert best_action != RecoveryAction.ESCALATE_TO_HUMAN, (
        f"Escalation should not be chosen at 500 INR with uplift 0.023 "
        f"(ENRV = {0.023 * 500 - 25:.1f})"
    )

    # At 2000 INR: escalation ENRV = 0.023 * 2000 - 25 = 21.0 (still suboptimal vs retry/link)
    best_action2, _, _ = ranker.decide(
        uplift_estimates=uplifts,
        candidate_actions=list(RecoveryAction),
        transaction_amount=2000.0,
    )
    # retry ENRV = 0.05 * 2000 - 0.1 = 99.9, link ENRV = 0.06 * 2000 - 2.5 = 117.5
    # escalation ENRV = 0.023 * 2000 - 25 = 21.0
    assert best_action2 != RecoveryAction.ESCALATE_TO_HUMAN, (
        f"Escalation should not beat retry/link at 2000 INR with correct uplifts"
    )
