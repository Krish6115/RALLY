"""
Evaluation metrics for PaymentPulse (Task 5 Audit).

Computes:
- Total and Mean Expected Net Recovered Value (ENRV) via Doubly Robust estimator.
- Standalone IPS and Direct Method (DM) estimates.
- Standard Error and 95% Confidence Interval for DR estimates.
- Incremental ENRV over No-Recovery (Baseline 1).
- Incremental ENRV over Rule-Based (Baseline 3).
- Action distributions, intervention rate, and self-cure reference metrics.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


class Evaluator:
    """Computes business and ML causal evaluation metrics."""

    def __init__(self, df_eval: pd.DataFrame):
        self.df = df_eval

    def compute_metrics(
        self,
        policy_name: str,
        policy_actions: np.ndarray,
        dr_scores: np.ndarray,
        ips_scores: np.ndarray,
        dm_scores: np.ndarray,
    ) -> dict[str, float]:
        """
        Compute full causal and business metrics for a policy.
        """
        n_events = len(self.df)
        if n_events == 0:
            raise ValueError("Evaluation dataset cannot be empty.")

        # --- DR Value Metrics ---
        total_enrv = float(np.sum(dr_scores))
        mean_enrv = float(np.mean(dr_scores))
        std_enrv = float(np.std(dr_scores))
        se_enrv = std_enrv / np.sqrt(n_events)
        ci95_low = mean_enrv - 1.96 * se_enrv
        ci95_high = mean_enrv + 1.96 * se_enrv

        # --- IPS and DM Metrics ---
        mean_ips = float(np.mean(ips_scores))
        mean_dm = float(np.mean(dm_scores))

        # --- Policy Behavior Metrics ---
        action_series = pd.Series(policy_actions)
        action_counts = action_series.value_counts().to_dict()

        do_nothing_count = action_counts.get("do_nothing", 0)
        intervention_rate = 1.0 - (do_nothing_count / n_events)

        # Baseline self-cure rate in the evaluation dataset
        self_cure_rate = float(self.df["was_self_cure"].mean()) if "was_self_cure" in self.df else 0.0

        return {
            "policy": policy_name,
            "total_enrv_inr": total_enrv,
            "mean_enrv_inr": mean_enrv,
            "dr_se_inr": se_enrv,
            "dr_ci95_low_inr": ci95_low,
            "dr_ci95_high_inr": ci95_high,
            "mean_ips_inr": mean_ips,
            "mean_dm_inr": mean_dm,
            "intervention_rate": intervention_rate,
            "self_cure_rate": self_cure_rate,
            # Action distribution
            "retry_rate": action_counts.get("retry_now", 0) / n_events,
            "wait_rate": sum(action_counts.get(a, 0) for a in ["wait_2min", "wait_5min", "wait_10min"]) / n_events,
            "link_rate": action_counts.get("send_payment_link", 0) / n_events,
            "switch_method_rate": sum(action_counts.get(a, 0) for a in ["switch_upi_app", "switch_to_card"]) / n_events,
            "escalate_rate": action_counts.get("escalate_to_human", 0) / n_events,
            **{f"count_{k}": v for k, v in action_counts.items()},
        }
