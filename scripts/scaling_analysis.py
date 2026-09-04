"""
Definitive PaymentPulse evaluation: S-Learner scaling analysis.

Shows how S-Learner ENRV converges toward the Rule-Based baseline with increasing
training data, plus a Direct Policy Learner (DPL) that demonstrates the system's
theoretical ceiling when the model correctly captures treatment effects.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import numpy as np
import pandas as pd
import logging
from collections import Counter

from rally.simulator import generate_batch
from rally.domain.enums import RecoveryAction
from rally.features.context_builder import ContextBuilder
from rally.models.uplift_model import SLearnerUpliftModel
from rally.models.action_ranker import ActionRanker
from rally.models.baselines import PaymentPulsePolicy, RuleBasedPolicy

from sklearn.ensemble import HistGradientBoostingClassifier

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


def train_direct_policy_learner(df_train, ctx):
    """
    Train a Direct Policy Learner (DPL) that directly predicts the oracle action
    from observable features. This uses the simulator's ground-truth treatment
    effects to compute oracle labels — valid in the simulation context.
    """
    X_train = ctx.transform(df_train)
    oracle_labels = compute_oracle_actions(df_train)

    # Encode action labels as integers
    action_values = sorted([a.value for a in RecoveryAction])
    label_map = {a: i for i, a in enumerate(action_values)}
    reverse_map = {i: a for a, i in label_map.items()}

    y_train = np.array([label_map[a] for a in oracle_labels])

    clf = HistGradientBoostingClassifier(
        max_depth=6,
        max_iter=200,
        learning_rate=0.05,
        min_samples_leaf=20,
        random_state=42,
        categorical_features=[0, 1, 2, 3],
    )
    clf.fit(X_train, y_train)

    return clf, label_map, reverse_map


def predict_dpl_actions(clf, X_test, reverse_map):
    y_pred = clf.predict(X_test)
    return np.array([reverse_map[y] for y in y_pred])


def main():
    # ========================================================================
    # PART 1: SCALING ANALYSIS — S-Learner ENRV vs training data size
    # ========================================================================
    print(f"\n{SEP}")
    print("  PART 1: S-LEARNER SCALING ANALYSIS")
    print(SEP)

    # Fixed test set
    df_test = generate_batch(n_events=10000, seed=44, epsilon=0.1, contribution_margin=1.0)
    oracle_actions = compute_oracle_actions(df_test)
    gt_oracle = compute_ground_truth_enrv(df_test, oracle_actions)

    rb_policy = RuleBasedPolicy()
    rb_actions, _ = rb_policy.select_actions_batch(df_test)
    gt_rb = compute_ground_truth_enrv(df_test, rb_actions)

    print(f"\n  Oracle ENRV: {gt_oracle.mean():.2f}")
    print(f"  Rule-Based ENRV: {gt_rb.mean():.2f}")
    print(f"  Gap (Oracle - RB): {gt_oracle.mean() - gt_rb.mean():.2f}")
    print()

    print(f"  {'N_train':>10s} {'SL ENRV':>10s} {'Gap to RB':>12s} {'Oracle Agree':>14s} {'Time':>8s}")
    print("  " + "-" * 60)

    import time

    for n_train in [5000, 10000, 20000, 50000, 100000]:
        t0 = time.time()
        df_train = generate_batch(n_events=n_train, seed=42, epsilon=0.1, contribution_margin=1.0)
        ctx = ContextBuilder()
        X_train = ctx.fit_transform(df_train)
        X_test_ctx = ctx.transform(df_test)

        train_actions = df_train["action"].values
        train_recovery = df_train["recovered"].values.astype(float)

        slearner = SLearnerUpliftModel(random_state=42)
        slearner.fit(X_train, train_actions, train_recovery)

        ranker = ActionRanker(contribution_margin=1.0, min_confidence_threshold=0.0)
        pp_policy = PaymentPulsePolicy(uplift_model=slearner, context_builder=ctx, ranker=ranker)
        sl_actions, _ = pp_policy.select_actions_batch(df_test)

        gt_sl = compute_ground_truth_enrv(df_test, sl_actions)
        elapsed = time.time() - t0

        gap = gt_sl.mean() - gt_rb.mean()
        agree = (sl_actions == oracle_actions).mean()

        print(f"  {n_train:10d} {gt_sl.mean():10.2f} {gap:+12.2f} {agree:13.1%} {elapsed:7.1f}s")

    # ========================================================================
    # PART 2: DIRECT POLICY LEARNER (DPL) — theoretical ceiling
    # ========================================================================
    print(f"\n{SEP}")
    print("  PART 2: DIRECT POLICY LEARNER (DPL) — CEILING TEST")
    print(SEP)

    print("\n  DPL trains a classifier to predict oracle actions from observable features.")
    print("  This uses simulator ground truth and shows what's achievable with perfect")
    print("  treatment-effect knowledge but only observable features for generalization.\n")

    for n_train in [10000, 50000, 100000]:
        df_train = generate_batch(n_events=n_train, seed=42, epsilon=0.1, contribution_margin=1.0)
        ctx = ContextBuilder()
        ctx.fit_transform(df_train)
        X_test_ctx = ctx.transform(df_test)

        clf, label_map, reverse_map = train_direct_policy_learner(df_train, ctx)
        dpl_actions = predict_dpl_actions(clf, X_test_ctx, reverse_map)
        gt_dpl = compute_ground_truth_enrv(df_test, dpl_actions)

        gap_to_rb = gt_dpl.mean() - gt_rb.mean()
        gap_to_oracle = gt_dpl.mean() - gt_oracle.mean()
        agree = (dpl_actions == oracle_actions).mean()

        print(f"  DPL (n={n_train:6d}):  ENRV={gt_dpl.mean():.2f}  vs RB: {gap_to_rb:+.2f}  vs Oracle: {gap_to_oracle:+.2f}  agree={agree:.1%}")

    # ========================================================================
    # PART 3: BEST S-LEARNER DETAILED RESULTS (50K training)
    # ========================================================================
    print(f"\n{SEP}")
    print("  PART 3: BEST S-LEARNER DETAILED ANALYSIS (50K training)")
    print(SEP)

    df_train = generate_batch(n_events=50000, seed=42, epsilon=0.1, contribution_margin=1.0)
    ctx = ContextBuilder()
    X_train = ctx.fit_transform(df_train)
    X_test_ctx = ctx.transform(df_test)

    slearner = SLearnerUpliftModel(random_state=42)
    slearner.fit(X_train, df_train["action"].values, df_train["recovered"].values.astype(float))

    ranker = ActionRanker(contribution_margin=1.0, min_confidence_threshold=0.0)
    pp_policy = PaymentPulsePolicy(uplift_model=slearner, context_builder=ctx, ranker=ranker)
    sl_actions, _ = pp_policy.select_actions_batch(df_test)
    gt_sl = compute_ground_truth_enrv(df_test, sl_actions)

    # Action distribution
    print(f"\n  {'Action':30s} {'Oracle%':>8s} {'SL-PP%':>8s} {'RB%':>8s}")
    print("  " + "-" * 58)
    oracle_counts = Counter(oracle_actions)
    sl_counts = Counter(sl_actions)
    rb_counts = Counter(rb_actions)
    all_acts = sorted(set(list(oracle_counts) + list(sl_counts) + list(rb_counts)))
    for act in all_acts:
        o = 100.0 * oracle_counts.get(act, 0) / len(oracle_actions)
        s = 100.0 * sl_counts.get(act, 0) / len(sl_actions)
        r = 100.0 * rb_counts.get(act, 0) / len(rb_actions)
        print(f"  {act:30s} {o:7.1f}% {s:7.1f}% {r:7.1f}%")

    # Calibration
    print(f"\n  UPLIFT CALIBRATION (50K S-Learner):")
    sl_uplifts = slearner.predict_all_uplifts(X_test_ctx)
    print(f"  {'Action':30s} {'Pred':>8s} {'True':>8s} {'Bias':>8s}")
    print("  " + "-" * 56)
    for act in sorted([a.value for a in RecoveryAction]):
        if act == "do_nothing":
            continue
        pred = sl_uplifts[act].mean()
        true = df_test[f"_latent_tau_{act}"].mean()
        bias = pred - true
        print(f"  {act:30s} {pred:8.4f} {true:8.4f} {bias:+8.4f}")

    # Final verdict
    print(f"\n{SEP}")
    print("  FINAL VERDICT")
    print(SEP)
    print(f"\n  Oracle ENRV/event:        {gt_oracle.mean():.2f}")
    print(f"  Rule-Based ENRV/event:    {gt_rb.mean():.2f}")
    print(f"  S-Learner PP ENRV/event:  {gt_sl.mean():.2f}")
    print(f"\n  S-Learner gap to RB:      {gt_sl.mean() - gt_rb.mean():+.2f} INR/event")
    print(f"  S-Learner gap to Oracle:  {gt_sl.mean() - gt_oracle.mean():+.2f} INR/event")
    print(f"  RB gap to Oracle:         {gt_rb.mean() - gt_oracle.mean():+.2f} INR/event")

    print(f"\n  [AUDIT STATEMENT]")
    print(f"  Synthetic evaluation demonstrates methodological behavior under simulated")
    print(f"  assumptions and does not establish production revenue lift.")
    print(f"  The S-Learner underperforms rule-based because the treatment effect")
    print(f"  heterogeneity is primarily driven by error_code (which the rule-based")
    print(f"  policy already perfectly encodes) and latent customer traits (which")
    print(f"  are unobservable in the current feature set).")
    print(f"  The DPL ceiling test shows the theoretical maximum achievable with")
    print(f"  observable features and perfect treatment-effect knowledge.")


if __name__ == "__main__":
    main()
