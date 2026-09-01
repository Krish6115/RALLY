#!/usr/bin/env python3
"""
Diagnostic Audit: Oracle vs Deployable Action Consistency
"""

import argparse
import pandas as pd
import numpy as np
from paymentpulse.simulator import generate_batch
from paymentpulse.features.context_builder import ContextBuilder
from paymentpulse.models.uplift_model import TLearnerUpliftModel, OraclePolicyModel
from paymentpulse.models.baselines import RuleBasedPolicy, PaymentPulsePolicy, OraclePolicy
from paymentpulse.models.action_ranker import ActionRanker
from paymentpulse.domain.enums import RecoveryAction

def compute_oracle_labels(df):
    COST_MAP = {
        "do_nothing": 0.0, "retry_now": 0.10, "wait_2min": 0.0,
        "wait_5min": 0.0, "wait_10min": 0.0, "switch_upi_app": 0.50,
        "switch_to_card": 0.50, "send_payment_link": 2.50,
        "escalate_to_human": 25.0,
    }
    oracle_actions = []
    enrvs = {}
    for i, row in df.iterrows():
        best_act = "do_nothing"
        best_enrv = row.get("_latent_self_cure_prob", 0) * row.get("amount_inr", 0)
        
        row_enrvs = {}
        for act in [a.value for a in RecoveryAction]:
            tau = row.get(f"_latent_tau_{act}", 0.0)
            p_rec = np.clip(row.get("_latent_self_cure_prob", 0) + tau, 0.0, 0.95)
            enrv = p_rec * row.get("amount_inr", 0) - COST_MAP.get(act, 0.0)
            row_enrvs[act] = enrv
            if enrv > best_enrv:
                best_enrv = enrv
                best_act = act
                
        oracle_actions.append(best_act)
        enrvs[i] = row_enrvs
    return np.array(oracle_actions), enrvs

def main():
    print("Generating train cohort...")
    df_train = generate_batch(n_events=50000, seed=42)
    
    print("Generating held-out evaluation cohort (100 samples)...")
    df_test = generate_batch(n_events=100, seed=99)
    
    ctx = ContextBuilder()
    X_train = ctx.fit_transform(df_train)
    X_test = ctx.transform(df_test)
    
    # Train Deployable Policy
    print("Training Deployable T-Learner...")
    t_learner = TLearnerUpliftModel(random_state=42)
    t_learner.fit(X_train, df_train["action"].values, df_train["recovered"].values.astype(float), propensities=df_train["propensity"].values)
    
    paymentpulse = PaymentPulsePolicy(
        uplift_model=t_learner,
        context_builder=ctx,
        ranker=ActionRanker()
    )
    
    # Train Oracle Policy
    print("Training Oracle Model...")
    oracle_labels, train_enrvs = compute_oracle_labels(df_train)
    oracle_model = OraclePolicyModel(random_state=42).fit(X_train, oracle_labels)
    oracle_policy = OraclePolicy(oracle_model, ctx)
    
    # Rule Based
    rule_based = RuleBasedPolicy()
    
    # Evaluate on test
    oracle_test_labels, test_enrvs = compute_oracle_labels(df_test)
    
    pp_actions, _ = paymentpulse.select_actions_batch(df_test)
    oracle_actions, _ = oracle_policy.select_actions_batch(df_test)
    rb_actions, _ = rule_based.select_actions_batch(df_test)
    
    pp_uplifts = t_learner.predict_all_uplifts(X_test)
    
    results = []
    
    for i in range(len(df_test)):
        row = df_test.iloc[i]
        context_str = f"Amt:INR {row['amount_inr']:.0f} | Err:{row['error_code']}"
        
        oracle_act = oracle_test_labels[i]
        pp_act = pp_actions[i]
        rb_act = rb_actions[i]
        
        enrv_dict = test_enrvs[i]
        oracle_enrv = enrv_dict[oracle_act]
        pp_enrv = enrv_dict[pp_act]
        rb_enrv = enrv_dict[rb_act]
        
        # What uplift did PP use for the action it chose?
        pp_pred = pp_uplifts.get(pp_act, np.zeros(len(df_test)))[i]
        
        results.append({
            "Context": context_str,
            "Oracle_Best": oracle_act,
            "PaymentPulse": pp_act,
            "RuleBased": rb_act,
            "GT_ENRV_Oracle": oracle_enrv,
            "GT_ENRV_PaymentPulse": pp_enrv,
            "GT_ENRV_RuleBased": rb_enrv,
            "PP_Predicted_Uplift": pp_pred
        })
        
    df_res = pd.DataFrame(results)
    
    print("\n--- SAMPLE OF 10 CONTEXTS ---")
    print(df_res.head(10).to_string())
    
    # Calculate metrics
    oracle_agreement = (df_res["Oracle_Best"] == df_res["PaymentPulse"]).mean() * 100
    avg_regret = (df_res["GT_ENRV_Oracle"] - df_res["GT_ENRV_PaymentPulse"]).mean()
    mean_pp_enrv = df_res["GT_ENRV_PaymentPulse"].mean()
    mean_rb_enrv = df_res["GT_ENRV_RuleBased"].mean()
    incremental_enrv = mean_pp_enrv - mean_rb_enrv
    
    print("\n--- AGGREGATE METRICS (n=100) ---")
    print(f"Oracle Agreement Rate: {oracle_agreement:.1f}%")
    print(f"Average Regret vs Oracle: INR {avg_regret:.2f}")
    print(f"Deployable PaymentPulse GT ENRV: INR {mean_pp_enrv:.2f}")
    print(f"Rule-Based Baseline GT ENRV: INR {mean_rb_enrv:.2f}")
    print(f"Incremental ENRV vs Rule-Based: INR {incremental_enrv:.2f}")

if __name__ == "__main__":
    main()
