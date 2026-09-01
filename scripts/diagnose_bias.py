"""
Diagnose where the S-Learner's uplift calibration breaks down.

For each error_code × action pair, compare:
- Mean predicted uplift (from S-Learner)
- Mean true tau (from latent ground truth)
- Rule-based action for that error code
- Oracle action distribution for that error code

This reveals whether the model is miscalibrating *uniformly* or for *specific* error codes.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import numpy as np
import pandas as pd
from collections import Counter

from paymentpulse.simulator import generate_batch
from paymentpulse.domain.enums import RecoveryAction
from paymentpulse.features.context_builder import ContextBuilder
from paymentpulse.models.uplift_model import SLearnerUpliftModel
from paymentpulse.models.action_ranker import ActionRanker
from paymentpulse.models.baselines import PaymentPulsePolicy, RuleBasedPolicy
from paymentpulse.simulator.error_taxonomy import get_error_by_code

cost_map = {
    "do_nothing": 0.0, "retry_now": 0.10, "wait_2min": 0.0,
    "wait_5min": 0.0, "wait_10min": 0.0, "switch_upi_app": 0.50,
    "switch_to_card": 0.50, "send_payment_link": 2.50,
    "escalate_to_human": 25.0,
}


def compute_oracle_action(row):
    best_act = "do_nothing"
    best_enrv = row["_latent_self_cure_prob"] * row["amount_inr"] - 0.0
    for act in [a.value for a in RecoveryAction]:
        tau = row.get(f"_latent_tau_{act}", 0.0)
        p_rec = np.clip(row["_latent_self_cure_prob"] + tau, 0.0, 0.95)
        enrv = p_rec * row["amount_inr"] - cost_map.get(act, 0.0)
        if enrv > best_enrv:
            best_enrv = enrv
            best_act = act
    return best_act


def main():
    print("Generating data...")
    df_train = generate_batch(n_events=20000, seed=42, epsilon=0.1, contribution_margin=1.0)
    df_test = generate_batch(n_events=10000, seed=44, epsilon=0.1, contribution_margin=1.0)

    ctx = ContextBuilder()
    X_train = ctx.fit_transform(df_train)
    X_test = ctx.transform(df_test)

    train_actions = df_train["action"].values
    train_recovery = df_train["recovered"].values.astype(float)

    print("Training S-Learner...")
    slearner = SLearnerUpliftModel(random_state=42)
    slearner.fit(X_train, train_actions, train_recovery)

    ranker = ActionRanker(contribution_margin=1.0, min_confidence_threshold=0.0)
    pp_policy = PaymentPulsePolicy(uplift_model=slearner, context_builder=ctx, ranker=ranker)
    rb_policy = RuleBasedPolicy()

    pp_actions, _ = pp_policy.select_actions_batch(df_test)
    rb_actions, _ = rb_policy.select_actions_batch(df_test)

    # Compute oracle actions
    oracle_actions = df_test.apply(compute_oracle_action, axis=1).values

    # Get predicted uplifts
    sl_uplifts = slearner.predict_all_uplifts(X_test)

    # ========================================================================
    # PER ERROR CODE ANALYSIS
    # ========================================================================
    error_codes = sorted(df_test["error_code"].unique())
    actions = sorted([a.value for a in RecoveryAction if a != RecoveryAction.DO_NOTHING])

    print("\n" + "=" * 120)
    print("  PER-ERROR-CODE UPLIFT CALIBRATION")
    print("=" * 120)

    for ec in error_codes:
        mask = df_test["error_code"] == ec
        n = mask.sum()
        entry = get_error_by_code(ec)
        rb_action = entry.rule_based_action.value if entry else "unknown"

        print(f"\n  Error: {ec} (n={n}, RB action={rb_action})")
        print(f"  {'Action':25s} {'Pred Uplift':>12s} {'True Tau':>12s} {'Bias':>12s} {'PP%':>8s} {'Oracle%':>8s}")
        print("  " + "-" * 80)

        ec_oracle = oracle_actions[mask.values]
        ec_pp = pp_actions[mask.values]
        oracle_dist = Counter(ec_oracle)
        pp_dist = Counter(ec_pp)

        for act in actions:
            pred_uplift = sl_uplifts[act][mask.values].mean()
            true_tau = df_test.loc[mask, f"_latent_tau_{act}"].mean()
            bias = pred_uplift - true_tau
            pp_pct = 100.0 * pp_dist.get(act, 0) / n
            oracle_pct = 100.0 * oracle_dist.get(act, 0) / n

            flag = ""
            if abs(bias) > 0.03:
                flag = " !!BIAS!!"
            if act == rb_action:
                flag += " [RB]"

            print(f"  {act:25s} {pred_uplift:12.4f} {true_tau:12.4f} {bias:+12.4f} {pp_pct:7.1f}% {oracle_pct:7.1f}%{flag}")

    # ========================================================================
    # TOP-LEVEL SUMMARY: Where does PP disagree and lose?
    # ========================================================================
    print("\n" + "=" * 120)
    print("  WHERE PP DISAGREES WITH ORACLE, BY ERROR CODE")
    print("=" * 120)

    for ec in error_codes:
        mask = (df_test["error_code"] == ec).values
        n = mask.sum()
        ec_oracle = oracle_actions[mask]
        ec_pp = pp_actions[mask]
        disagree = ec_oracle != ec_pp
        n_disagree = disagree.sum()
        agreement = 1.0 - n_disagree / n if n > 0 else 0

        # What does PP pick instead of oracle?
        if n_disagree > 0:
            pp_wrong = ec_pp[disagree]
            oracle_wanted = ec_oracle[disagree]
            pp_wrong_dist = Counter(pp_wrong)
            oracle_wanted_dist = Counter(oracle_wanted)
            top_pp_wrong = pp_wrong_dist.most_common(3)
            top_oracle_wanted = oracle_wanted_dist.most_common(3)

            pp_str = ", ".join([f"{a}={c}" for a, c in top_pp_wrong])
            oracle_str = ", ".join([f"{a}={c}" for a, c in top_oracle_wanted])
            print(f"  {ec:45s}  agree={agreement:.1%}  PP picks: {pp_str}   Oracle wants: {oracle_str}")


if __name__ == "__main__":
    main()
