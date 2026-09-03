"""
Out-of-Sample Evaluation Runner (Task 5 Audit).

Guarantees:
1. Complete train / test cohort independence (no hyperparameter tuning on test cohort).
2. Evaluates all 5 baselines using Doubly Robust, IPS, and Direct Method estimators.
3. Computes statistical confidence intervals for DR values.
4. Outputs mandatory synthetic evaluation disclaimer.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
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
    """Runs the out-of-sample evaluation suite across all 5 baselines."""

    DISCLAIMER = (
        "\n[AUDIT STATEMENT]\n"
        "Synthetic evaluation demonstrates methodological behavior under simulated "
        "assumptions and does not establish production revenue lift.\n"
    )

    def __init__(
        self,
        df_train: pd.DataFrame,
        df_test: pd.DataFrame,
        config: EvaluationConfig,
    ):
        self.df_train = df_train
        self.df_test = df_test
        self.config = config

        logger.info(
            f"Initializing evaluation runner: Train cohort ({len(df_train)} events) "
            f"| Test cohort ({len(df_test)} events)"
        )

        # 1. Fit DR estimator on train cohort ONLY
        self.dr_estimator = DoublyRobustEstimator(df_train)

        # 2. Metrics calculator evaluates on test cohort ONLY
        self.evaluator = Evaluator(df_test)
        self.results: list[dict] = []

    def run_all_baselines(
        self,
        paymentpulse_policy: PaymentPulsePolicy,
        timing_bandit_policy: TimingOnlyBanditPolicy,
        oracle_policy,
    ) -> pd.DataFrame:
        """
        Runs and evaluates all baselines on the out-of-sample test cohort.
        """
        baselines = [
            NoRecoveryPolicy(),
            AlwaysRetryPolicy(),
            RuleBasedPolicy(),
            timing_bandit_policy,
            paymentpulse_policy,
            oracle_policy,
        ]

        self.results = []
        
        # Helper to compute exact ground-truth ENRV if latent variables exist
        def compute_gt_enrv(df, actions):
            gt_vals = []
            cost_map = {
                "do_nothing": 0.0, "retry_now": 0.10, "wait_2min": 0.0,
                "wait_5min": 0.0, "wait_10min": 0.0, "switch_upi_app": 0.50,
                "switch_to_card": 0.50, "send_payment_link": 2.50,
                "escalate_to_human": 25.0,
            }
            for i, row in df.iterrows():
                act = actions[i]
                tau = row.get(f"_latent_tau_{act}", 0.0)
                p_rec = np.clip(row.get("_latent_self_cure_prob", 0.0) + tau, 0.0, 0.95)
                enrv = p_rec * row.get("amount_inr", 0.0) - cost_map.get(act, 0.0)
                gt_vals.append(enrv)
            return np.sum(gt_vals), np.mean(gt_vals)

        for policy in baselines:
            logger.info(f"Evaluating policy: {policy.name}")

            # 1. Target policy selects actions on untouched test cohort
            actions, propensities = policy.select_actions_batch(self.df_test)

            # 2. Off-policy evaluation on test cohort
            scores_dict = self.dr_estimator.evaluate_policy(
                df_eval=self.df_test,
                target_actions=actions,
            )

            # 3. Compute business & causal metrics
            metrics = self.evaluator.compute_metrics(
                policy_name=policy.name,
                policy_actions=actions,
                dr_scores=scores_dict["dr_scores"],
                ips_scores=scores_dict["ips_scores"],
                dm_scores=scores_dict["dm_scores"],
            )
            
            # 4. Compute Ground-Truth Simulator ENRV
            if "_latent_self_cure_prob" in self.df_test.columns:
                gt_total, gt_mean = compute_gt_enrv(self.df_test, actions)
                metrics["gt_total_enrv"] = gt_total
                metrics["gt_mean_enrv"] = gt_mean
            else:
                metrics["gt_total_enrv"] = np.nan
                metrics["gt_mean_enrv"] = np.nan

            self.results.append(metrics)

        df_results = pd.DataFrame(self.results)

        # Compute incremental metrics relative to Baselines 1 and 3
        no_rec_val = df_results[df_results["policy"] == "no_recovery"]["total_enrv_inr"].values[0]
        rule_based_val = df_results[df_results["policy"] == "rule_based"]["total_enrv_inr"].values[0]

        df_results["lift_vs_no_recovery_inr"] = df_results["total_enrv_inr"] - no_rec_val
        df_results["lift_vs_rule_based_inr"] = df_results["total_enrv_inr"] - rule_based_val

        return df_results

    def print_comparison_table(self, df_results: Optional[pd.DataFrame] = None):
        """Prints the formatted baseline comparison table matching Section M."""
        df_res = df_results if df_results is not None else pd.DataFrame(self.results)
        if df_res.empty:
            logger.warning("No evaluation results to display.")
            return

        df_display = pd.DataFrame({
            "Policy": df_res["policy"],
            "GT ENRV/Event": df_res["gt_mean_enrv"].round(2),
            "DR ENRV/Event (Est)": df_res["mean_enrv_inr"].round(2),
            "DR 95% CI (Est)": (
                "[" + df_res["dr_ci95_low_inr"].round(2).astype(str) + ", " +
                df_res["dr_ci95_high_inr"].round(2).astype(str) + "]"
            ),
            "Intervention Rate": (df_res["intervention_rate"] * 100).round(1).astype(str) + "%",
            "DM Est": df_res["mean_dm_inr"].round(2),
            "IPS Est": df_res["mean_ips_inr"].round(2),
        })

        print("\n=== Out-of-Sample Causal Evaluation Results (Expected Net Recovered Value) ===")
        print(tabulate(df_display, headers="keys", tablefmt="github", showindex=False))
        print(self.DISCLAIMER)
        print("=================================================================================\n")
