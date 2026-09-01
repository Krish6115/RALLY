"""
Unit tests for TimingOnlyBanditPolicy (Task 4 Audit).

Verifies:
1. Policy does NOT collapse to 100% retry_now.
2. Policy distinguishes immediate retry vs delayed retry when gateway/bank downtime occurs.
3. Batch decisioning maintains non-degenerate timing distribution.
"""

import pandas as pd
import numpy as np
from paymentpulse.models.baselines import TimingOnlyBanditPolicy
from paymentpulse.domain.enums import RecoveryAction
from paymentpulse.features.context_builder import ContextBuilder


def test_timing_bandit_distinguishes_immediate_vs_delayed_retry():
    """
    Proves that TimingOnlyBanditPolicy selects a wait action (wait_2min/5min/10min)
    when downtime is active, and immediate retry_now when gateway is healthy.
    """
    policy = TimingOnlyBanditPolicy()
    legal_actions = [
        RecoveryAction.RETRY_NOW,
        RecoveryAction.WAIT_2MIN,
        RecoveryAction.WAIT_5MIN,
        RecoveryAction.WAIT_10MIN,
    ]

    # Case 1: Gateway is down -> must prefer waiting
    event_down = {"is_gateway_down": True, "is_bank_down": False}
    action_down, _ = policy.select_action(event_down, legal_actions)
    assert action_down in (RecoveryAction.WAIT_2MIN, RecoveryAction.WAIT_5MIN, RecoveryAction.WAIT_10MIN)
    assert action_down != RecoveryAction.RETRY_NOW

    # Case 2: Gateway is healthy -> must prefer immediate retry
    event_healthy = {"is_gateway_down": False, "is_bank_down": False}
    action_healthy, _ = policy.select_action(event_healthy, legal_actions)
    assert action_healthy == RecoveryAction.RETRY_NOW


def test_timing_bandit_batch_training_and_diversity():
    """
    Trains TimingOnlyBanditPolicy on synthetic feature matrix and verifies
    that batch decisions produce a diverse, non-degenerate set of timing actions.
    """
    ctx = ContextBuilder()

    np.random.seed(42)
    n_samples = 800
    df = pd.DataFrame({
        "amount_inr": np.random.uniform(100, 2000, n_samples),
        "amount_bucket": ["small"] * n_samples,
        "method": ["upi"] * n_samples,
        "instrument": ["vpa"] * n_samples,
        "error_code": ["GATEWAY_ERROR"] * n_samples,
        "error_source": ["gateway"] * n_samples,
        "attempt_number": [1] * n_samples,
        "hour_of_day": [14.0] * n_samples,
        "is_evening": [False] * n_samples,
        "is_weekend": [False] * n_samples,
        "is_gateway_down": [i % 2 == 0 for i in range(n_samples)],  # 50% downtime
        "is_bank_down": [False] * n_samples,
        "downtime_severity": [0.8 if i % 2 == 0 else 0.0 for i in range(n_samples)],
        "prior_attempts_this_session": [0] * n_samples,
        "prior_recoveries_this_session": [0] * n_samples,
        "time_since_session_start_seconds": [30.0] * n_samples,
        "session_time_remaining_seconds": [800.0] * n_samples,
    })

    X = ctx.fit_transform(df)

    actions = []
    outcomes = []
    timing_arm_choices = [
        RecoveryAction.RETRY_NOW.value,
        RecoveryAction.WAIT_2MIN.value,
        RecoveryAction.WAIT_5MIN.value,
        RecoveryAction.WAIT_10MIN.value,
    ]

    for i in range(n_samples):
        act = np.random.choice(timing_arm_choices)
        is_down = df.iloc[i]["is_gateway_down"]
        if is_down:
            prob = 0.90 if act in ("wait_5min", "wait_10min") else 0.05
        else:
            prob = 0.90 if act == "retry_now" else 0.15

        outcome = 1.0 if np.random.random() < prob else 0.0
        actions.append(act)
        outcomes.append(outcome)

    policy = TimingOnlyBanditPolicy(context_builder=ctx)
    policy.fit(X, np.array(actions), np.array(outcomes))

    selected_actions, _ = policy.select_actions_batch(df)

    unique_actions = set(selected_actions)
    # Proves the policy does NOT collapse to only 1 action!
    assert len(unique_actions) > 1, f"Timing bandit collapsed to only: {unique_actions}"
    assert "retry_now" in unique_actions
    assert any(a in unique_actions for a in ["wait_2min", "wait_5min", "wait_10min"])
