"""
Evaluation sanity checks.

Section L / 0.4 requires explicitly checking the claimed uplift against
published industry bounds. If the simulator says we get a 40 percentage
point uplift, the simulator is broken (leaking the answer).
"""

from __future__ import annotations

import logging
import pandas as pd

from paymentpulse.config import EvaluationConfig

logger = logging.getLogger(__name__)


class SanityChecker:
    """Verifies evaluation results against realistic bounds."""

    def __init__(self, config: EvaluationConfig):
        self.config = config

    def check_results(self, df_results: pd.DataFrame) -> list[str]:
        """
        Run sanity checks on the evaluation results.

        Returns a list of warning messages. If empty, all checks passed.
        """
        warnings = []

        # Find key baselines
        try:
            res_no_recovery = df_results[df_results["policy"] == "no_recovery"].iloc[0]
            res_rule_based = df_results[df_results["policy"] == "rule_based"].iloc[0]
            res_paymentpulse = df_results[df_results["policy"] == "paymentpulse"].iloc[0]
        except IndexError:
            return ["Missing required baselines in results DataFrame."]

        # 1. Self-cure rate check
        # No-recovery policy's "recovered_amount" proxy (since ENRV = recovered - 0)
        # We need the base success rate from the simulator data to really know,
        # but if ENRV per failure is > 50% of average transaction size, it's suspiciously high.
        # This is a rough proxy check.

        # 2. Uplift vs Rule-Based (The main check from 0.4)
        enrv_rb = res_rule_based["total_enrv_inr"]
        enrv_pp = res_paymentpulse["total_enrv_inr"]
        
        if enrv_rb > 0:
            uplift_pct = ((enrv_pp - enrv_rb) / enrv_rb) * 100
            
            # Note: This is uplift in ENRV, not raw recovery rate percentage points,
            # but the same principle applies: if it's > 20-30% better than the
            # optimized rule-based system, it's highly suspicious.
            if uplift_pct > 30.0:
                warnings.append(
                    f"RED FLAG: PaymentPulse ENRV uplift is {uplift_pct:.1f}% "
                    f"over rule-based. This is suspiciously high compared to "
                    f"published industry ranges (Adyen Auto Rescue: 4-10%). "
                    f"Check for feature leakage in the simulator."
                )
            
            if uplift_pct < 0:
                warnings.append(
                    "WARNING: PaymentPulse policy performed worse than rule-based. "
                    "Check uplift model training."
                )

        # 3. Intervention rate check
        # PaymentPulse shouldn't be intervening 100% of the time, because
        # do_nothing should win when net_value is negative.
        pp_intervention_rate = res_paymentpulse["intervention_rate"]
        if pp_intervention_rate > 0.99:
            warnings.append(
                "WARNING: PaymentPulse intervenes on almost every failure. "
                "Cost calibration might be too low, or it failed to learn self-cure."
            )
            
        return warnings
