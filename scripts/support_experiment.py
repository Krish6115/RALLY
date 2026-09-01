#!/usr/bin/env python3
"""
Controlled Investigation of Logging Policy Observational Support.

Experiment:
Train two identical T-Learner models on two different logging policies:
- Policy A (Current): Epsilon=0.05 (mostly rule-based)
- Policy B (High Support): Epsilon=0.40 (highly exploratory)

Evaluate both on the EXACT SAME untouched test cohort (seed=44).
"""

import logging
import pandas as pd
import numpy as np
from tabulate import tabulate

from paymentpulse.simulator import generate_batch
from paymentpulse.features.context_builder import ContextBuilder
from paymentpulse.models.uplift_model import TLearnerUpliftModel
from paymentpulse.models.action_ranker import ActionRanker
from paymentpulse.models.baselines import PaymentPulsePolicy, RuleBasedPolicy
from paymentpulse.evaluation.off_policy import DoublyRobustEstimator
from paymentpulse.evaluation.metrics import Evaluator
from paymentpulse.domain.enums import RecoveryAction

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

def compute_gt_enrv(df, actions):
    gt_vals = []
    cost_map = {
        "do_nothing": 0.0, "retry_now": 0.10, "wait_2min": 0.0,
        "wait_5min": 0.0, "wait_10min": 0.0, "switch_upi_app": 0.50,
        "switch_to_card": 0.50, "send_payment_link": 2.50,
        "escalate_to_human": 25.0,
    }
    oracle_actions = []
    
    for i, row in df.iterrows():
        # GT calculation
        act = actions[i]
        tau = row.get(f"_latent_tau_{act}", 0.0)
        p_rec = np.clip(row.get("_latent_self_cure_prob", 0.0) + tau, 0.0, 0.95)
        enrv = p_rec * row.get("amount_inr", 0.0) - cost_map.get(act, 0.0)
        gt_vals.append(enrv)
        
        # Oracle best action calculation
        best_act = "do_nothing"
        best_enrv = row.get("_latent_self_cure_prob", 0.0) * row.get("amount_inr", 0.0)
        for a in [act.value for act in RecoveryAction]:
            a_tau = row.get(f"_latent_tau_{a}", 0.0)
            a_p_rec = np.clip(row.get("_latent_self_cure_prob", 0.0) + a_tau, 0.0, 0.95)
            a_enrv = a_p_rec * row.get("amount_inr", 0.0) - cost_map.get(a, 0.0)
            if a_enrv > best_enrv:
                best_enrv = a_enrv
                best_act = a
        oracle_actions.append(best_act)
        
    return np.mean(gt_vals), np.array(oracle_actions)

def analyze_cohort(df, name):
    print(f"\n--- {name} Cohort Support Analysis ---")
    actions = df["action"]
    counts = actions.value_counts()
    freq = counts / len(df)
    min_prop = df.groupby("action")["propensity"].min()
    
    analysis = pd.DataFrame({
        "Training Obs": counts,
        "Frequency": freq,
        "Min Propensity": min_prop
    }).fillna(0)
    
    print(tabulate(analysis, headers="keys", tablefmt="github"))
    return analysis

def main():
    N_TRAIN = 20000
    N_TEST = 10000
    
    # 1. Generate Datasets
    logger.info("Generating Training Cohort A (Epsilon = 0.05)...")
    df_train_a = generate_batch(n_events=N_TRAIN, seed=42, epsilon=0.05)
    
    logger.info("Generating Training Cohort B (Epsilon = 0.40)...")
    df_train_b = generate_batch(n_events=N_TRAIN, seed=52, epsilon=0.40)
    
    logger.info("Generating Untouched Test Cohort (Epsilon = 0.05)...")
    df_test = generate_batch(n_events=N_TEST, seed=44, epsilon=0.05)
    
    # Analyze Support
    analyze_cohort(df_train_a, "Cohort A (Eps=0.05)")
    analyze_cohort(df_train_b, "Cohort B (Eps=0.40)")
    
    ctx = ContextBuilder()
    X_train_a = ctx.fit_transform(df_train_a)
    X_train_b = ctx.fit_transform(df_train_b) # Same features
    
    # 2. Train Models
    logger.info("Training Model A...")
    model_a = TLearnerUpliftModel(random_state=42)
    model_a.fit(X_train_a, df_train_a["action"].values, df_train_a["recovered"].values.astype(float), df_train_a["propensity"].values)
    
    logger.info("Training Model B...")
    model_b = TLearnerUpliftModel(random_state=42)
    model_b.fit(X_train_b, df_train_b["action"].values, df_train_b["recovered"].values.astype(float), df_train_b["propensity"].values)
    
    policy_a = PaymentPulsePolicy(uplift_model=model_a, context_builder=ctx, ranker=ActionRanker())
    policy_a.name = "PP_Model_A"
    
    policy_b = PaymentPulsePolicy(uplift_model=model_b, context_builder=ctx, ranker=ActionRanker())
    policy_b.name = "PP_Model_B"
    
    rule_based = RuleBasedPolicy()
    
    # 3. Evaluate strictly on df_test
    logger.info("Evaluating on untouched test cohort...")
    baselines = [rule_based, policy_a, policy_b]
    dr_estimator = DoublyRobustEstimator(df_train_a) # Use train A for eval reward model
    evaluator = Evaluator(df_test)
    
    results = []
    
    for policy in baselines:
        actions, _ = policy.select_actions_batch(df_test)
        
        scores = dr_estimator.evaluate_policy(df_test, actions)
        
        metrics = evaluator.compute_metrics(
            policy.name, actions, scores["dr_scores"], scores["ips_scores"], scores["dm_scores"]
        )
        
        gt_mean, oracle_actions = compute_gt_enrv(df_test, actions)
        
        oracle_agreement = np.mean(actions == oracle_actions) * 100
        
        # Action distribution
        unique, counts = np.unique(actions, return_counts=True)
        dist = dict(zip(unique, counts))
        
        metrics["gt_mean"] = gt_mean
        metrics["oracle_agreement"] = oracle_agreement
        metrics["action_dist"] = str(dist)
        
        results.append(metrics)
        
    df_res = pd.DataFrame(results)
    
    # Calculate Incremental against RB
    rb_gt = df_res[df_res["policy"] == "rule_based"]["gt_mean"].values[0]
    df_res["incremental_vs_rb"] = df_res["gt_mean"] - rb_gt
    
    print("\n=== EXPERIMENTAL EVALUATION RESULTS ===")
    df_display = pd.DataFrame({
        "Policy": df_res["policy"],
        "GT ENRV": df_res["gt_mean"].round(2),
        "Inc vs RB": df_res["incremental_vs_rb"].round(2),
        "Oracle Match": df_res["oracle_agreement"].round(1).astype(str) + "%",
        "DR Est (CI)": df_res["mean_enrv_inr"].round(2).astype(str) + " [" + df_res["dr_ci95_low_inr"].round(2).astype(str) + ", " + df_res["dr_ci95_high_inr"].round(2).astype(str) + "]",
        "IPS Est": df_res["mean_ips_inr"].round(2),
        "DM Est": df_res["mean_dm_inr"].round(2)
    })
    
    print(tabulate(df_display, headers="keys", tablefmt="github", showindex=False))
    
    print("\n--- Action Distributions on Test ---")
    for _, row in df_res.iterrows():
        print(f"{row['policy']}: {row['action_dist']}")

if __name__ == "__main__":
    main()
