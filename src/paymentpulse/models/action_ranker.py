"""
Action ranker â€” the core decision function.

Implements the exact decision function from Section C:
    a* = argmax_{a âˆˆ AllowedActions(x)} [ Ï„Ì‚(x,a) âˆ’ cost(a) ]
    a* = âˆ… (do_nothing) whenever the best net value â‰¤ 0

This is where the ML model's uplift estimates become actionable decisions.
The ranker scores all legal actions by expected incremental net value,
then returns the ranking for the policy engine to apply hard constraints.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from paymentpulse.simulator.models import RecoveryAction


@dataclass
class ActionScore:
    """Score for one candidate action."""
    action: RecoveryAction
    estimated_uplift: float  # Ï„Ì‚(x, a) â€” incremental value over do_nothing
    estimated_cost: float  # Direct + friction cost
    net_value: float  # uplift - cost
    confidence: float  # Model confidence (for reporting, not decisioning)


class ActionRanker:
    """
    Ranks candidate actions by expected incremental net value.

    The ranker:
    1. Takes uplift estimates from the model for each candidate action
    2. Subtracts action costs
    3. Ranks by net value
    4. Returns do_nothing if no action has positive net value

    The ranker does NOT enforce safety constraints â€” that's the policy
    engine's job. The ranker only cares about expected value.
    """

    # Action costs in INR (matching the simulator's cost model for consistency)
    ACTION_COSTS: dict[RecoveryAction, float] = {
        RecoveryAction.DO_NOTHING: 0.0,
        RecoveryAction.RETRY_NOW: 0.10,
        RecoveryAction.WAIT_2MIN: 0.0,
        RecoveryAction.WAIT_5MIN: 0.0,
        RecoveryAction.WAIT_10MIN: 0.0,
        RecoveryAction.SWITCH_UPI_APP: 0.50,
        RecoveryAction.SWITCH_TO_CARD: 0.50,
        RecoveryAction.SEND_PAYMENT_LINK: 2.50,
        RecoveryAction.ESCALATE_TO_HUMAN: 25.0,
    }

    def rank(
        self,
        uplift_estimates: dict[str, float],
        candidate_actions: list[RecoveryAction],
        transaction_amount: float = 0.0,
    ) -> list[ActionScore]:
        """
        Rank candidate actions by net expected value.

        Args:
            uplift_estimates: Dict mapping action_name â†’ Ï„Ì‚(x, a).
            candidate_actions: Legal actions to rank among.
            transaction_amount: Used for confidence calibration.

        Returns:
            List of ActionScore sorted by net_value descending.
            First element is the recommended action.
        """
        scores = []

        for action in candidate_actions:
            uplift = uplift_estimates.get(action.value, 0.0)
            cost = self.ACTION_COSTS.get(action, 0.0)

            # Scale uplift by transaction amount to get expected value in INR
            # Ï„Ì‚ is a probability uplift; multiply by amount to get INR value
            ev_inr = uplift * transaction_amount
            net = ev_inr - cost

            # Confidence: rough heuristic based on uplift magnitude
            # (A proper model would output variance; this is a placeholder)
            confidence = min(1.0, abs(uplift) / 0.3) if uplift > 0 else 0.1

            scores.append(ActionScore(
                action=action,
                estimated_uplift=uplift,
                estimated_cost=cost,
                net_value=net,
                confidence=confidence,
            ))

        # Sort by net value descending
        scores.sort(key=lambda s: s.net_value, reverse=True)

        return scores

    def decide(
        self,
        uplift_estimates: dict[str, float],
        candidate_actions: list[RecoveryAction],
        transaction_amount: float = 0.0,
    ) -> tuple[RecoveryAction, ActionScore, list[ActionScore]]:
        """
        Make the final decision: best action, its score, and full ranking.

        Returns do_nothing if no action has positive net value.

        Returns:
            (best_action, best_score, full_ranking)
        """
        rankings = self.rank(uplift_estimates, candidate_actions, transaction_amount)

        if not rankings:
            # No candidates â€” do nothing
            do_nothing_score = ActionScore(
                action=RecoveryAction.DO_NOTHING,
                estimated_uplift=0.0,
                estimated_cost=0.0,
                net_value=0.0,
                confidence=1.0,
            )
            return RecoveryAction.DO_NOTHING, do_nothing_score, [do_nothing_score]

        best = rankings[0]

        # If best net value â‰¤ 0, do nothing is strictly better
        if best.net_value <= 0:
            do_nothing_score = ActionScore(
                action=RecoveryAction.DO_NOTHING,
                estimated_uplift=0.0,
                estimated_cost=0.0,
                net_value=0.0,
                confidence=1.0,
            )
            return RecoveryAction.DO_NOTHING, do_nothing_score, rankings

        return best.action, best, rankings
