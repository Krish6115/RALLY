"""
Evaluation metrics for PaymentPulse.

Primary metric (from Section L):
    Expected Net Recovered Value (ENRV) =
        Î£(recovered_gmv) âˆ’ Î£(intervention_costs) âˆ’ Î£(friction_costs)
"""

from __future__ import annotations

import numpy as np
import pandas as pd


class Evaluator:
    """Computes business and ML metrics for a given policy's predictions."""

    def __init__(self, df_logged: pd.DataFrame):
        self.df = df_logged

    def compute_metrics(
        self,
        policy_name: str,
        policy_actions: np.ndarray,
        estimated_values: np.ndarray,  # From DoublyRobustEstimator
    ) -> dict[str, float]:
        """
        Compute all metrics for a policy.

        Args:
            policy_name: Name of the policy.
            policy_actions: Array of actions selected by the policy.
            estimated_values: DR estimates of net_value for these actions.
        """
        # --- Value Metrics (Estimated via off-policy DR) ---
        total_enrv = float(np.sum(estimated_values))
        mean_enrv = float(np.mean(estimated_values))

        # --- Policy Behavior Metrics ---
        n_events = len(self.df)
        action_counts = pd.Series(policy_actions).value_counts().to_dict()

        intervention_rate = 1.0 - (action_counts.get("do_nothing", 0) / n_events)

        # How often does it just retry?
        retry_rate = action_counts.get("retry_now", 0) / n_events

        # How often does it send a link?
        link_rate = action_counts.get("send_payment_link", 0) / n_events

        return {
            "policy": policy_name,
            "total_enrv_inr": total_enrv,
            "mean_enrv_inr": mean_enrv,
            "intervention_rate": intervention_rate,
            "retry_rate": retry_rate,
            "link_rate": link_rate,
            # Raw counts for deep dive
            **{f"count_{k}": v for k, v in action_counts.items()}
        }
