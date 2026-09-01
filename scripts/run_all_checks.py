"""
Master script to verify system integrity and reproducibility.

Implements Phase 22:
- Runs pytest to verify the state machine and safety constraints.
- Runs the causal support experiment.
- Evaluates the policy baselines.
"""

import subprocess
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

def run_cmd(cmd: str, name: str) -> bool:
    logging.info(f"=== Running {name} ===")
    try:
        result = subprocess.run(cmd, shell=True, check=True, text=True)
        logging.info(f"[{name}] PASSED\n")
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"[{name}] FAILED with code {e.returncode}\n")
        return False

def main():
    checks = [
        ("py -m pytest tests/", "Safety & Unit Tests"),
        ("py scripts/support_experiment.py", "Causal Logging Support Experiment"),
        ("py scripts/action_consistency_audit.py", "Oracle Causal Leakage Check"),
        # The demo script runs the evaluation and outputs the table
        ("py scripts/run_demo.py", "Full Synthetic Pipeline Evaluation"),
    ]

    all_passed = True
    for cmd, name in checks:
        if not run_cmd(cmd, name):
            all_passed = False

    if all_passed:
        logging.info("ALL REPRODUCIBILITY CHECKS PASSED. Backend is demo-ready.")
        sys.exit(0)
    else:
        logging.error("SOME CHECKS FAILED. Do not proceed to frontend.")
        sys.exit(1)

if __name__ == "__main__":
    main()
