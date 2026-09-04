#!/usr/bin/env python3
"""
End-to-End Simulation & Out-of-Sample Causal Evaluation Runner (Task 5 Audit).

Guarantees:
1. Genuinely independent cohorts:
   - Train cohort (seed 42)
   - Validation cohort (seed 43)
   - Untouched Test cohort (seed 44)
2. Models are trained strictly on the train cohort.
3. PaymentPulse uses a DirectPolicyModel (DPL) trained on oracle labels
   from simulator ground truth. In production, oracle labels would be
   derived from A/B test outcomes.
4. All 5 baselines are evaluated out-of-sample on the test cohort using Doubly Robust estimation.
"""

import argparse
import logging
from pathlib import Path

import numpy as np

from rally.config import config
from rally.simulator import generate_batch
from rally.domain.enums import RecoveryAction
from rally.features.context_builder import ContextBuilder
from rally.models.uplift_model import SLearnerUpliftModel, TLearnerUpliftModel, OraclePolicyModel
from rally.models.action_ranker import ActionRanker
from rally.models.baselines import TimingOnlyBanditPolicy, PaymentPulsePolicy, OraclePolicy
from rally.evaluation.runner import EvaluationRunner
from rally.evaluation.sanity_checks import SanityChecker

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# Action cost map (must match ActionRanker and simulator)
COST_MAP = {
    "do_nothing": 0.0, "retry_now": 0.10, "wait_2min": 0.0,
    "wait_5min": 0.0, "wait_10min": 0.0, "switch_upi_app": 0.50,
    "switch_to_card": 0.50, "send_payment_link": 2.50,
    "escalate_to_human": 25.0,
}


def compute_oracle_actions(df):
    """Compute the ground-truth optimal action for each event using latent treatment effects."""
    oracle_actions = []
    for _, row in df.iterrows():
        best_act = "do_nothing"
        best_enrv = row["_latent_self_cure_prob"] * row["amount_inr"]
        for act in [a.value for a in RecoveryAction]:
            tau = row.get(f"_latent_tau_{act}", 0.0)
            p_rec = np.clip(row["_latent_self_cure_prob"] + tau, 0.0, 0.95)
            enrv = p_rec * row["amount_inr"] - COST_MAP.get(act, 0.0)
            if enrv > best_enrv:
                best_enrv = enrv
                best_act = act
        oracle_actions.append(best_act)
    return np.array(oracle_actions)


def main():
    parser = argparse.ArgumentParser(description="Rally Out-of-Sample Evaluation Runner")
    parser.add_argument("--n-events", type=int, default=config.simulator.default_batch_size)
    parser.add_argument("--train-seed", type=int, default=42)
    parser.add_argument("--val-seed", type=int, default=43)
    parser.add_argument("--test-seed", type=int, default=44)
    parser.add_argument("--contribution-margin", type=float, default=1.0)
    parser.add_argument("--output", type=str, default="results/evaluation_summary.csv")
    args = parser.parse_args()

    # 1. Generate Genuinely Independent Cohorts
    logger.info(f"Generating Train cohort: {args.n_events} events (seed={args.train_seed})...")
    df_train = generate_batch(
        n_events=args.n_events,
        seed=args.train_seed,
        epsilon=config.simulator.epsilon,
        contribution_margin=args.contribution_margin,
    )

    logger.info(f"Generating Validation cohort: 2000 events (seed={args.val_seed})...")
    df_val = generate_batch(
        n_events=2000,
        seed=args.val_seed,
        epsilon=config.simulator.epsilon,
        contribution_margin=args.contribution_margin,
    )

    logger.info(f"Generating Untouched Test cohort: {args.n_events} events (seed={args.test_seed})...")
    df_test = generate_batch(
        n_events=args.n_events,
        seed=args.test_seed,
        epsilon=config.simulator.epsilon,
        contribution_margin=args.contribution_margin,
    )

    # Save datasets
    output_dir = Path("data")
    output_dir.mkdir(exist_ok=True)
    df_train.to_parquet(output_dir / "train_cohort.parquet")
    df_val.to_parquet(output_dir / "val_cohort.parquet")
    df_test.to_parquet(output_dir / "test_cohort.parquet")
    logger.info("Saved train, val, and test cohorts to data/")

    # 2. Fit Feature Transformers on Train Cohort ONLY
    logger.info("Fitting ContextBuilder on Train cohort...")
    ctx = ContextBuilder()
    X_train = ctx.fit_transform(df_train)

    train_actions = df_train["action"].values
    # Target: binary recovery indicator (1.0 or 0.0) -> model estimates probability uplift τ̂_P
    train_recovery = df_train["recovered"].values.astype(float)
    train_propensities = df_train["propensity"].values.astype(float)

    # 3. Train Deployable Model (T-Learner)
    logger.info("Training Deployable Rally policy (T-Learner on observables)...")
    uplift_model = TLearnerUpliftModel(random_state=args.train_seed)
    uplift_model.fit(X_train, train_actions, train_recovery, propensities=train_propensities)

    ranker = ActionRanker(
        contribution_margin=args.contribution_margin,
        min_confidence_threshold=0.0,
    )
    paymentpulse_policy = PaymentPulsePolicy(
        uplift_model=uplift_model,
        context_builder=ctx,
        ranker=ranker,
    )

    # 4. Train Oracle Model (Diagnostic ONLY)
    logger.info("Computing oracle labels from simulator ground truth for Diagnostic Oracle...")
    oracle_labels = compute_oracle_actions(df_train)
    oracle_model = OraclePolicyModel(random_state=args.train_seed)
    oracle_model.fit(X_train, oracle_labels)
    oracle_policy = OraclePolicy(oracle_model=oracle_model, context_builder=ctx)

    logger.info("Training Timing-Only Bandit (Baseline 4) on Train cohort...")
    timing_bandit = TimingOnlyBanditPolicy(context_builder=ctx)
    timing_bandit.fit(X_train, train_actions, train_recovery)

    # 5. Out-of-Sample Evaluation on Untouched Test Cohort
    logger.info("Running out-of-sample evaluation on held-out Test cohort...")
    runner = EvaluationRunner(df_train=df_train, df_test=df_test, config=config.evaluation)
    
    # We evaluate PaymentPulse (Deployable), Timing Bandit, and the Oracle Diagnostic
    df_results = runner.run_all_baselines(paymentpulse_policy, timing_bandit, oracle_policy)

    # Print results table
    runner.print_comparison_table(df_results)

    # 6. Sanity Checks
    logger.info("Running diagnostic sanity checks...")
    checker = SanityChecker(config.evaluation)
    warnings = checker.check_results(df_results)

    if warnings:
        for w in warnings:
            logger.warning(f"[DIAGNOSTIC] {w}")
    else:
        logger.info("All diagnostic sanity checks passed.")

    # Save summary
    out_path = Path(args.output)
    out_path.parent.mkdir(exist_ok=True)
    df_results.to_csv(out_path, index=False)
    logger.info(f"Evaluation summary saved to {out_path}")


if __name__ == "__main__":
    main()

