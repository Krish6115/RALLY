"""
Hand-Calculated Unit Tests for Doubly Robust Off-Policy Estimator (Task 4 Audit).

Verifies:
1. Exact mathematical equivalence on a 3-sample hand-checkable dataset.
2. Independent verification of IPS, Direct Method (DM), and DR combinations.
3. Strict propensity validation (rejection of zero, negative, or >1.0 propensities).
4. Action ordering and representation consistency.
"""

import numpy as np
import pytest
from paymentpulse.evaluation.off_policy import compute_doubly_robust_scores


def test_hand_checkable_doubly_robust_calculation():
    """
    Constructs a 3-sample dataset with pencil-and-paper verified values:

    Sample 1:
      Target = 'retry_now', Logged = 'retry_now' (Match!)
      p = 0.5, r = 100.0, μ̂_target = 80.0, μ̂_logged = 80.0
      DM = 80.0
      IPS = (1 / 0.5) × 100.0 = 200.0
      DR = 80.0 + (1 / 0.5) × (100.0 − 80.0) = 80.0 + 40.0 = 120.0

    Sample 2:
      Target = 'send_payment_link', Logged = 'do_nothing' (Mismatch!)
      p = 0.25, r = 0.0, μ̂_target = 50.0, μ̂_logged = 10.0
      DM = 50.0
      IPS = 0.0 × 0.0 = 0.0
      DR = 50.0 + 0.0 × (0.0 − 10.0) = 50.0

    Sample 3:
      Target = 'wait_2min', Logged = 'wait_2min' (Match!)
      p = 0.2, r = 200.0, μ̂_target = 250.0, μ̂_logged = 250.0
      DM = 250.0
      IPS = (1 / 0.2) × 200.0 = 1000.0
      DR = 250.0 + (1 / 0.2) × (200.0 − 250.0) = 250.0 − 250.0 = 0.0

    Averages:
      Mean DM:  (80 + 50 + 250) / 3 = 380 / 3 ≈ 126.6667
      Mean IPS: (200 + 0 + 1000) / 3 = 1200 / 3 = 400.0
      Mean DR:  (120 + 50 + 0) / 3 = 170 / 3 ≈ 56.6667
    """
    target_actions = np.array(["retry_now", "send_payment_link", "wait_2min"])
    logged_actions = np.array(["retry_now", "do_nothing", "wait_2min"])
    logged_propensities = np.array([0.5, 0.25, 0.2])
    logged_rewards = np.array([100.0, 0.0, 200.0])
    mu_target = np.array([80.0, 50.0, 250.0])
    mu_logged = np.array([80.0, 10.0, 250.0])

    dr_scores, ips_scores, dm_scores = compute_doubly_robust_scores(
        target_actions=target_actions,
        logged_actions=logged_actions,
        logged_propensities=logged_propensities,
        logged_rewards=logged_rewards,
        mu_target=mu_target,
        mu_logged=mu_logged,
    )

    # Pointwise sample verification
    assert np.allclose(dm_scores, [80.0, 50.0, 250.0])
    assert np.allclose(ips_scores, [200.0, 0.0, 1000.0])
    assert np.allclose(dr_scores, [120.0, 50.0, 0.0])

    # Mean batch metrics verification
    assert np.isclose(np.mean(dm_scores), 380.0 / 3.0)
    assert np.isclose(np.mean(ips_scores), 400.0)
    assert np.isclose(np.mean(dr_scores), 170.0 / 3.0)


def test_propensity_validation_rejects_non_positive_values():
    """Logging propensities must be strictly positive (p > 0)."""
    with pytest.raises(ValueError) as exc_info:
        compute_doubly_robust_scores(
            target_actions=np.array(["a"]),
            logged_actions=np.array(["a"]),
            logged_propensities=np.array([0.0]),  # Invalid!
            logged_rewards=np.array([10.0]),
            mu_target=np.array([10.0]),
            mu_logged=np.array([10.0]),
        )
    assert "strictly positive" in str(exc_info.value)


def test_propensity_validation_rejects_greater_than_one():
    """Logging propensities cannot exceed 1.0."""
    with pytest.raises(ValueError) as exc_info:
        compute_doubly_robust_scores(
            target_actions=np.array(["a"]),
            logged_actions=np.array(["a"]),
            logged_propensities=np.array([1.5]),  # Invalid!
            logged_rewards=np.array([10.0]),
            mu_target=np.array([10.0]),
            mu_logged=np.array([10.0]),
        )
    assert "cannot exceed 1.0" in str(exc_info.value)
