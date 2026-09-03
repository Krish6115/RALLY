"""
Action ranker — the core decision function with strict unit consistency.

Unit Convention (Section 4 Audit):
----------------------------------
- Uplift: τ̂_P(x, a) ∈ [-1.0, 1.0] — Dimensionless probability uplift over DO_NOTHING.
- Transaction Amount: GMV in INR (> 0).
- Contribution Margin: Merchant margin fraction ∈ (0.0, 1.0] (default 0.20 = 20%).
- Recovered Contribution: τ̂_P(x, a) × amount_inr × contribution_margin (in INR).
- Intervention Cost: Direct channel + friction cost (in INR).
- Expected Net Recovered Value (ENRV): Recovered Contribution − Intervention Cost (in INR).

Governing Invariant:
    If best ENRV ≤ 0, DO_NOTHING is strictly optimal.
    Self-cure is never rewarded (DO_NOTHING is reference arm; τ̂_P measures incremental lift).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from paymentpulse.domain.enums import RecoveryAction

logger = logging.getLogger(__name__)


@dataclass
class ActionScore:
    """Score for one candidate action with explicit units."""
    action: RecoveryAction
    estimated_uplift: float         # τ̂_P(x, a) ∈ [-1.0, 1.0] (probability uplift over control)
    recovered_gmv: float            # τ̂_P × amount_inr (INR)
    recovered_contribution: float   # recovered_gmv × contribution_margin (INR)
    estimated_cost: float           # Direct channel + friction cost (INR)
    net_value: float                # recovered_contribution − estimated_cost (INR)
    confidence: float               # Model confidence score ∈ [0.0, 1.0]


class ActionRanker:
    """
    Ranks candidate actions by Expected Net Recovered Value (ENRV).
    """

    # Action costs in INR (calibrated to real API and channel messaging costs)
    DEFAULT_ACTION_COSTS: dict[RecoveryAction, float] = {
        RecoveryAction.DO_NOTHING: 0.0,
        RecoveryAction.RETRY_NOW: 0.10,          # Internal gateway retry API cost
        RecoveryAction.WAIT_2MIN: 0.0,           # Passive scheduler wait
        RecoveryAction.WAIT_5MIN: 0.0,           # Passive scheduler wait
        RecoveryAction.WAIT_10MIN: 0.0,          # Passive scheduler wait
        RecoveryAction.SWITCH_UPI_APP: 0.50,     # Dynamic UPI intent link notification
        RecoveryAction.SWITCH_TO_CARD: 0.50,     # Payment method switch link
        RecoveryAction.SEND_PAYMENT_LINK: 2.50,  # SMS / WhatsApp notification cost + friction
        RecoveryAction.ESCALATE_TO_HUMAN: 25.0,  # Customer support agent time
    }

    def __init__(
        self,
        contribution_margin: float = 0.20,
        min_confidence_threshold: float = 0.10,
        action_costs: Optional[dict[RecoveryAction, float]] = None,
    ):
        if not (0.0 < contribution_margin <= 1.0):
            raise ValueError(f"Contribution margin must be in (0.0, 1.0], got {contribution_margin}")
        self.contribution_margin = contribution_margin
        self.min_confidence_threshold = min_confidence_threshold
        self.action_costs = action_costs or self.DEFAULT_ACTION_COSTS

    def rank(
        self,
        uplift_estimates: dict[str, float],
        candidate_actions: list[RecoveryAction],
        transaction_amount: float = 0.0,
    ) -> list[ActionScore]:
        """
        Rank candidate actions by ENRV in INR.

        Args:
            uplift_estimates: Dict mapping action_name → τ̂_P(x, a) ∈ [-1.0, 1.0].
            candidate_actions: Legal actions allowed by policy engine.
            transaction_amount: Gross transaction amount in INR.

        Returns:
            List of ActionScore sorted by net_value descending.
        """
        if transaction_amount < 0:
            raise ValueError(f"Transaction amount cannot be negative: {transaction_amount}")

        scores: list[ActionScore] = []

        for action in candidate_actions:
            if action == RecoveryAction.DO_NOTHING:
                # DO_NOTHING is reference control: uplift = 0, cost = 0, net = 0
                scores.append(ActionScore(
                    action=RecoveryAction.DO_NOTHING,
                    estimated_uplift=0.0,
                    recovered_gmv=0.0,
                    recovered_contribution=0.0,
                    estimated_cost=0.0,
                    net_value=0.0,
                    confidence=1.0,
                ))
                continue

            uplift = float(uplift_estimates.get(action.value, 0.0))

            # Unit safety assertion: Probability uplift MUST be in [-1.0, 1.0]
            # (allowing tiny floating-point tolerance ±0.05)
            if uplift < -1.05 or uplift > 1.05:
                raise ValueError(
                    f"FATAL UNIT MISMATCH: Action '{action.value}' has estimated uplift {uplift:.4f}. "
                    f"Uplift must be a probability in [-1.0, 1.0]. Passing INR directly will cause "
                    f"quadratic (INR²) scaling errors."
                )

            # Clamp to valid probability interval [-1.0, 1.0]
            uplift_clamped = max(-1.0, min(1.0, uplift))

            cost = self.action_costs.get(action, 0.0)

            # Clean dimensional arithmetic:
            # recovered_gmv [INR] = uplift [1] × amount [INR]
            recovered_gmv = uplift_clamped * transaction_amount

            # recovered_contribution [INR] = recovered_gmv [INR] × contribution_margin [1]
            recovered_contribution = recovered_gmv * self.contribution_margin

            # net_value [INR] = recovered_contribution [INR] − cost [INR]
            net_value = recovered_contribution - cost

            # Confidence score heuristic (higher magnitude uplift = higher confidence)
            confidence = min(1.0, max(0.05, abs(uplift_clamped) / 0.25))

            scores.append(ActionScore(
                action=action,
                estimated_uplift=uplift_clamped,
                recovered_gmv=round(recovered_gmv, 2),
                recovered_contribution=round(recovered_contribution, 2),
                estimated_cost=cost,
                net_value=round(net_value, 2),
                confidence=round(confidence, 4),
            ))

        # Sort descending by expected net recovered value
        scores.sort(key=lambda s: s.net_value, reverse=True)
        return scores

    def decide(
        self,
        uplift_estimates: dict[str, float],
        candidate_actions: list[RecoveryAction],
        transaction_amount: float = 0.0,
    ) -> tuple[RecoveryAction, ActionScore, list[ActionScore]]:
        """
        Selects the best legal action.
        Guarantees DO_NOTHING is returned if best net_value ≤ 0 or if confidence is too low.
        """
        rankings = self.rank(uplift_estimates, candidate_actions, transaction_amount)

        do_nothing_score = ActionScore(
            action=RecoveryAction.DO_NOTHING,
            estimated_uplift=0.0,
            recovered_gmv=0.0,
            recovered_contribution=0.0,
            estimated_cost=0.0,
            net_value=0.0,
            confidence=1.0,
        )

        if not rankings:
            return RecoveryAction.DO_NOTHING, do_nothing_score, [do_nothing_score]

        best = rankings[0]

        # Invariant 1: If best net value ≤ 0, DO_NOTHING wins
        if best.net_value <= 0:
            logger.info(
                f"[RANKER] Best action {best.action.value} has non-positive net value ({best.net_value} INR). "
                f"Selecting DO_NOTHING."
            )
            return RecoveryAction.DO_NOTHING, do_nothing_score, rankings

        # Invariant 2: Low-confidence fallback
        if best.confidence < self.min_confidence_threshold:
            logger.warning(
                f"[RANKER] Best action {best.action.value} confidence ({best.confidence:.3f}) below threshold "
                f"({self.min_confidence_threshold}). Falling back to DO_NOTHING."
            )
            return RecoveryAction.DO_NOTHING, do_nothing_score, rankings

        return best.action, best, rankings
