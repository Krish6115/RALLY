#!/usr/bin/env python3
"""
REMEDIATION VERIFICATION: S-Learner vs T-Learner calibration comparison.

After the causal red-team audit identified T-Learner per-arm overfitting
as the root cause of PaymentPulse underperformance, this script verifies
that the S-Learner fix resolves the calibration bias.
"""

import sys
import logging
from collections import Counter

import numpy as np
import pandas as pd

from rally.simulator import generate_batch
from rally.domain.enums import RecoveryAction
from rally.features.context_builder import ContextBuilder
from rally.models.uplift_model import TLearnerUpliftModel, SLearnerUpliftModel
from rally.models.action_ranker import ActionRanker
from rally.models.baselines import (
    NoRecoveryPolicy, AlwaysRetryPolicy, RuleBasedPolicy,
    TimingOnlyBanditPolicy, PaymentPulsePolicy,
)
from rally.evaluation.off_policy import DoublyRobustEstimator

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

SEP = "=" * 80

cost_map = {
    "do_nothing": 0.0, "retry_now": 0.10, "wait_2min": 0.0,
    "wait_5min": 0.0, "wait_10min": 0.0, "switch_upi_app": 0.50,
    "switch_to_card": 0.50, "send_payment_link": 2.50,
    "escalate_to_human": 25.0,
}


def compute_ground_truth_enrv(df, policy_actions, contribution_margin=1.0):
    enrvs = np.zeros(len(df))
    for i, (_, row) in enumerate(df.iterrows()):
        act = policy_actions[i]
        tau = row.get(f"_latent_tau_{act}", 0.0)
        self_cure = row["_latent_self_cure_prob"]
        p_recover = np.clip(self_cure + tau, 0.0, 0.95)
        amount = row["amount_inr"]
        cost = cost_map.get(act, 0.0)
        enrvs[i] = p_recover * amount * contribution_margin - cost
    return enrvs


def compute_oracle_actions(df):
    oracle_actions = []
    for _, row in df.iterrows():
        best_act = "do_nothing"
        best_enrv = row["_latent_self_cure_prob"] * row["amount_inr"] - 0.0
        for act in [a.value for a in RecoveryAction]:
            tau = row.get(f"_latent_tau_{act}", 0.0)
            p_rec = np.clip(row["_latent_self_cure_prob"] + tau, 0.0, 0.95)
            enrv = p_rec * row["amount_inr"] - cost_map.get(act, 0.0)
            if enrv > best_enrv:
                best_enrv = enrv
                best_act = act
        oracle_actions.append(best_act)
    return np.array(oracle_actions)


def main():
    print("Generating cohorts...")
    df_train = generate_batch(n_events=50000, seed=42, epsilon=0.1, contribution_margin=1.0)
    df_test = generate_batch(n_events=10000, seed=44, epsilon=0.1, contribution_margin=1.0)

    ctx = ContextBuilder()
    X_train = ctx.fit_transform(df_train)
    X_test = ctx.transform(df_test)

    train_actions = df_train["action"].values
    train_recovery = df_train["recovered"].values.astype(float)
    train_propensities = df_train["propensity"].values.astype(float)

    # ---- Train both models ----
    print("Training T-Learner...")
    tlearner = TLearnerUpliftModel(random_state=42)
    tlearner.fit(X_train, train_actions, train_recovery, propensities=train_propensities)

    print("Training S-Learner...")
    slearner = SLearnerUpliftModel(random_state=42)
    slearner.fit(X_train, train_actions, train_recovery, propensities=train_propensities)

    ranker = ActionRanker(contribution_margin=1.0, min_confidence_threshold=0.0)

    # ---- Build policies ----
    pp_tlearner = PaymentPulsePolicy(uplift_model=tlearner, context_builder=ctx, ranker=ranker)
    pp_slearner = PaymentPulsePolicy(uplift_model=slearner, context_builder=ctx, ranker=ranker)
    rb_policy = RuleBasedPolicy()

    # ---- Get actions ----
    tl_actions, _ = pp_tlearner.select_actions_batch(df_test)
    sl_actions, _ = pp_slearner.select_actions_batch(df_test)
    rb_actions, _ = rb_policy.select_actions_batch(df_test)
    oracle_actions = compute_oracle_actions(df_test)

    # ══════════════════════════════════════════════════════════════════════
    # SECTION 1: CALIBRATION COMPARISON
    # ══════════════════════════════════════════════════════════════════════
    print(f"\n{SEP}")
    print("  1. UPLIFT CALIBRATION: T-Learner vs S-Learner")
    print(SEP)

    tl_uplifts = tlearner.predict_all_uplifts(X_test)
    sl_uplifts = slearner.predict_all_uplifts(X_test)

    print(f"\n  {'Action':30s} {'TL pred':>10s} {'SL pred':>10s} {'True':>10s} {'TL bias':>10s} {'SL bias':>10s}")
    print("  " + "-" * 80)

    for act in sorted([a.value for a in RecoveryAction]):
        col = f"_latent_tau_{act}"
        if col not in df_test.columns:
            continue
        tl_mean = tl_uplifts.get(act, np.zeros(len(df_test))).mean()
        sl_mean = sl_uplifts.get(act, np.zeros(len(df_test))).mean()
        true_mean = df_test[col].mean()
        tl_bias = tl_mean - true_mean
        sl_bias = sl_mean - true_mean
        print(f"  {act:30s} {tl_mean:10.4f} {sl_mean:10.4f} {true_mean:10.4f} "
              f"{tl_bias:+10.4f} {sl_bias:+10.4f}")

    # ══════════════════════════════════════════════════════════════════════
    # SECTION 2: ACTION DISTRIBUTION COMPARISON
    # ══════════════════════════════════════════════════════════════════════
    print(f"\n{SEP}")
    print("  2. ACTION DISTRIBUTION COMPARISON")
    print(SEP)

    oracle_counts = Counter(oracle_actions)
    tl_counts = Counter(tl_actions)
    sl_counts = Counter(sl_actions)
    rb_counts = Counter(rb_actions)

    all_acts = sorted(set(list(oracle_counts) + list(tl_counts) + list(sl_counts) + list(rb_counts)))

    print(f"\n  {'Action':30s} {'Oracle%':>8s} {'TL-PP%':>8s} {'SL-PP%':>8s} {'RB%':>8s}")
    print("  " + "-" * 70)
    for act in all_acts:
        o = 100.0 * oracle_counts.get(act, 0) / len(oracle_actions)
        t = 100.0 * tl_counts.get(act, 0) / len(tl_actions)
        s = 100.0 * sl_counts.get(act, 0) / len(sl_actions)
        r = 100.0 * rb_counts.get(act, 0) / len(rb_actions)
        print(f"  {act:30s} {o:7.1f}% {t:7.1f}% {s:7.1f}% {r:7.1f}%")

    # ══════════════════════════════════════════════════════════════════════
    # SECTION 3: GROUND-TRUTH ENRV COMPARISON
    # ══════════════════════════════════════════════════════════════════════
    print(f"\n{SEP}")
    print("  3. GROUND-TRUTH ENRV COMPARISON")
    print(SEP)

    gt_oracle = compute_ground_truth_enrv(df_test, oracle_actions)
    gt_tl = compute_ground_truth_enrv(df_test, tl_actions)
    gt_sl = compute_ground_truth_enrv(df_test, sl_actions)
    gt_rb = compute_ground_truth_enrv(df_test, rb_actions)

    print(f"\n  {'Policy':30s} {'GT ENRV/event':>15s} {'vs Oracle':>12s} {'vs Rule-Based':>15s}")
    print("  " + "-" * 75)
    for name, gt, acts in [
        ("Oracle (optimal)", gt_oracle, oracle_actions),
        ("Rule-Based", gt_rb, rb_actions),
        ("PP (T-Learner, BEFORE)", gt_tl, tl_actions),
        ("PP (S-Learner, AFTER)", gt_sl, sl_actions),
    ]:
        vs_oracle = gt.mean() - gt_oracle.mean()
        vs_rb = gt.mean() - gt_rb.mean()
        print(f"  {name:30s} {gt.mean():15.2f} {vs_oracle:+12.2f} {vs_rb:+15.2f}")

    # Oracle agreement
    print(f"\n  Oracle agreement rates:")
    print(f"    T-Learner PP: {(tl_actions == oracle_actions).mean():.1%}")
    print(f"    S-Learner PP: {(sl_actions == oracle_actions).mean():.1%}")
    print(f"    Rule-Based:   {(rb_actions == oracle_actions).mean():.1%}")

    # ══════════════════════════════════════════════════════════════════════
    # SECTION 4: DR ESTIMATION COMPARISON
    # ══════════════════════════════════════════════════════════════════════
    print(f"\n{SEP}")
    print("  4. DOUBLY ROBUST ESTIMATION COMPARISON")
    print(SEP)

    dr_est = DoublyRobustEstimator(df_train)

    for name, acts in [
        ("Rule-Based", rb_actions),
        ("PP (T-Learner)", tl_actions),
        ("PP (S-Learner)", sl_actions),
    ]:
        scores = dr_est.evaluate_policy(df_eval=df_test, target_actions=acts)
        dr = scores["dr_scores"].mean()
        ips = scores["ips_scores"].mean()
        dm = scores["dm_scores"].mean()
        print(f"  {name:30s}  DR={dr:8.2f}  IPS={ips:8.2f}  DM={dm:8.2f}")

    # ══════════════════════════════════════════════════════════════════════
    # SECTION 5: DISAGREEMENT ANALYSIS (S-Learner vs Rule-Based)
    # ══════════════════════════════════════════════════════════════════════
    print(f"\n{SEP}")
    print("  5. S-LEARNER PP vs RULE-BASED DISAGREEMENT ANALYSIS")
    print(SEP)

    sl_disagree = sl_actions != rb_actions
    n_disagree = sl_disagree.sum()
    print(f"\n  Total disagreements: {n_disagree} ({100*n_disagree/len(sl_actions):.1f}%)")

    if n_disagree > 0:
        disagree_idx = np.where(sl_disagree)[0]
        gt_sl_d = compute_ground_truth_enrv(df_test.iloc[disagree_idx], sl_actions[disagree_idx])
        gt_rb_d = compute_ground_truth_enrv(df_test.iloc[disagree_idx], rb_actions[disagree_idx])
        sl_wins = (gt_sl_d > gt_rb_d).sum()
        rb_wins = (gt_rb_d > gt_sl_d).sum()
        ties = (gt_sl_d == gt_rb_d).sum()
        print(f"  S-Learner PP wins (GT): {sl_wins:6d} ({100*sl_wins/n_disagree:.1f}%)")
        print(f"  Rule-Based wins (GT):   {rb_wins:6d} ({100*rb_wins/n_disagree:.1f}%)")
        print(f"  Ties:                   {ties:6d}")
        print(f"  Mean GT ENRV (SL-PP):   {gt_sl_d.mean():.2f}")
        print(f"  Mean GT ENRV (RB):      {gt_rb_d.mean():.2f}")

    # ══════════════════════════════════════════════════════════════════════
    # SECTION 6: WAIT/ESCALATION OVERUSE CHECK
    # ══════════════════════════════════════════════════════════════════════
    print(f"\n{SEP}")
    print("  6. WAIT/ESCALATION OVERUSE CHECK (BEFORE vs AFTER)")
    print(SEP)

    wait_acts = ["wait_2min", "wait_5min", "wait_10min"]
    print(f"\n  Wait rate:")
    print(f"    T-Learner: {np.isin(tl_actions, wait_acts).mean():.1%}")
    print(f"    S-Learner: {np.isin(sl_actions, wait_acts).mean():.1%}")
    print(f"    Oracle:    {np.isin(oracle_actions, wait_acts).mean():.1%}")

    print(f"\n  Escalation rate:")
    print(f"    T-Learner: {(tl_actions == 'escalate_to_human').mean():.1%}")
    print(f"    S-Learner: {(sl_actions == 'escalate_to_human').mean():.1%}")
    print(f"    Oracle:    {(oracle_actions == 'escalate_to_human').mean():.1%}")

    # ══════════════════════════════════════════════════════════════════════
    # VERDICT
    # ══════════════════════════════════════════════════════════════════════
    print(f"\n{SEP}")
    print("  VERDICT")
    print(SEP)

    sl_gt_mean = gt_sl.mean()
    rb_gt_mean = gt_rb.mean()
    tl_gt_mean = gt_tl.mean()

    improvement_over_tl = sl_gt_mean - tl_gt_mean
    gap_to_rb = sl_gt_mean - rb_gt_mean

    print(f"\n  S-Learner GT ENRV improvement over T-Learner: {improvement_over_tl:+.2f} INR/event")
    print(f"  S-Learner GT ENRV gap to Rule-Based:          {gap_to_rb:+.2f} INR/event")

    if sl_gt_mean > rb_gt_mean:
        print("\n  --> S-LEARNER PP OUTPERFORMS RULE-BASED (ground truth).")
        print("  --> FIX IS EFFECTIVE. Ready for next stage.")
    elif sl_gt_mean > tl_gt_mean:
        print("\n  --> S-LEARNER PP IMPROVED but still UNDERPERFORMS Rule-Based.")
        print("  --> Partial fix. Additional model improvements needed.")
    else:
        print("\n  --> S-LEARNER PP DID NOT IMPROVE over T-Learner.")
        print("  --> Root cause may be deeper than per-arm overfitting.")

    print(f"\n  [AUDIT STATEMENT]")
    print(f"  Synthetic evaluation demonstrates methodological behavior under simulated")
    print(f"  assumptions and does not establish production revenue lift.")


if __name__ == "__main__":
    main()
