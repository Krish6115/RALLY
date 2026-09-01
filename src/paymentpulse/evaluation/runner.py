"""
End-to-end evaluation runner.

Runs all 5 baselines against a logged dataset and computes the comparison
table (Section M).
"""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd
from tabulate import tabulate

from paymentpulse.config import EvaluationConfig
from paymentpulse.models.baselines import (
    NoRecoveryPolicy,
    AlwaysRetryPolicy,
    RuleBasedPolicy,
    TimingOnlyBanditPolicy,
    PaymentPulsePolicy,
)
from paymentpulse.evaluation.off_policy import DoublyRobustEstimator
from paymentpulse.evaluation.metrics import Evaluator

logger = logging.getLogger(__name__)


class EvaluationRunner:
    """Runs the full evaluation suite."""

    def __init__(self, df_logged: pd.DataFrame, config: EvaluationConfig):
        self.df = df_logged
        self.config = config
        
        logger.info(f"Initializing evaluation runner with {len(df_logged)} events")
        
        # 1. Initialize off-policy estimator
        self.dr_estimator = DoublyRobustEstimator(df_logged)
        
        # 2. Initialize metrics evaluator
        self.evaluator = Evaluator(df_logged)
        
        self.results: list[dict] = []

    def run_all_baselines(
        self,
        paymentpulse_policy: PaymentPulsePolicy,
        timing_bandit_policy: TimingOnlyBanditPolicy,
    ) -> pd.DataFrame:
        """
        Run all 5 baselines and compile results.
        
        Args:
            paymentpulse_policy: Trained Baseline 5 policy.
            timing_bandit_policy: Trained Baseline 4 policy.
        """
        baselines = [
            NoRecoveryPolicy(),
            AlwaysRetryPolicy(),
            RuleBasedPolicy(),
            timing_bandit_policy,
            paymentpulse_policy,
        ]
        
        # We need legal actions for the batch. In a real system, we'd build
        # PolicyConstraints objects. Here, for bulk eval, we assume all actions
        # are legal except for those restricted by specific error codes (handled
        # by the ContextBuilder/Ranker internally).
        
        for policy in baselines:
            logger.info(f"Running evaluation for policy: {policy.name}")
            
            # 1. Get policy decisions for the whole batch
            actions, propensities = policy.select_actions_batch(self.df)
            
            # 2. Compute Doubly Robust estimates for these decisions
            estimated_values = self.dr_estimator.evaluate_policy(
                target_actions=actions,
                target_propensities=propensities,
            )
            
            # 3. Compute metrics
            metrics = self.evaluator.compute_metrics(
                policy_name=policy.name,
                policy_actions=actions,
                estimated_values=estimated_values,
            )
            
            self.results.append(metrics)
            
        return pd.DataFrame(self.results)

    def print_comparison_table(self):
        """Format results matching Section M of the research doc."""
        if not self.results:
            logger.warning("No results to print. Run evaluation first.")
            return

        df_res = pd.DataFrame(self.results)
        
        # Calculate uplift relative to Rule-Based (Baseline 3)
        rule_based_enrv = df_res[df_res["policy"] == "rule_based"]["total_enrv_inr"].values[0]
        
        df_display = pd.DataFrame({
            "Policy": df_res["policy"],
            "Total ENRV (INR)": df_res["total_enrv_inr"].round(2),
            "ENRV per Failure (INR)": df_res["mean_enrv_inr"].round(2),
            "Intervention Rate": (df_res["intervention_rate"] * 100).round(1).astype(str) + "%",
            "Uplift vs Rule-Based (INR)": (df_res["total_enrv_inr"] - rule_based_enrv).round(2),
        })
        
        print("\n=== Evaluation Results (Expected Net Recovered Value) ===")
        print(tabulate(df_display, headers="keys", tablefmt="github", showindex=False))
        print("=========================================================\n")
