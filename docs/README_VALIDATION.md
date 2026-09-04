# README Validation Report

Generated: 2026-09-04

## Verified Commands

| Command | Verified | Notes |
|---|---|---|
| `pip install -e ".[dev]"` | Yes | `pyproject.toml` confirms `[project.optional-dependencies] dev` |
| `scripts\start_app.cmd` | Yes | Launches backend (port 8000) + frontend (port 5173) |
| `python src/rally/api/server.py` | Yes | `uvicorn.run(app, host="0.0.0.0", port=8000)` at line 261 |
| `npm run dev` | Yes | Vite dev server on port 5173 |
| `python -m pytest tests/ -v` | Yes | 27 passed, 1 xfail, 31.17s |
| `python scripts/run_all_checks.py` | Yes | Script exists at `scripts/run_all_checks.py` |

## Verified URLs/Ports

| URL | Source |
|---|---|
| `http://localhost:8000` | `server.py` line 261: `uvicorn.run(app, host="0.0.0.0", port=8000)` |
| `http://localhost:5173` | Vite default dev server port, confirmed by running frontend |

## Verified Metrics (from `results/evaluation_summary.csv`)

| Policy | DR ENRV/Event (Est.) | DR 95% CI | Intervention Rate |
|---|---|---|---|
| No Recovery | ₹400.07 | [₹65.69, ₹734.45] | 0.0% |
| Rule-Based | ₹334.27 | [₹308.88, ₹359.66] | 98.5% |
| Rally | ₹228.45 | [₹67.11, ₹389.79] | 93.3% |
| Oracle Diagnostic | ₹299.43 | [₹204.91, ₹393.95] | 100.0% |

Source: `results/evaluation_summary.csv` columns `mean_enrv_inr`, `dr_ci95_low_inr`, `dr_ci95_high_inr`, `intervention_rate`

## Verified Test Count

- **27 passed**, 1 xfail (expected failure for `test_tlearner_uplift_bias_per_arm`)
- 10 test modules in `tests/`
- Run: `py -m pytest tests/ -v` on 2026-09-04
- Python 3.13, pytest

## Verified Repository Paths

| Path | Exists | Type |
|---|---|---|
| `src/rally/api/` | Yes | Directory (server.py, routes.py, webhooks.py) |
| `src/rally/config/` | Yes | Directory (settings.py) |
| `src/rally/domain/` | Yes | Directory (entities.py, enums.py, decisions.py) |
| `src/rally/evaluation/` | Yes | Directory (off_policy.py, runner.py, metrics.py, sanity_checks.py) |
| `src/rally/execution/` | Yes | Directory (action_executor.py, adapter.py, razorpay_client.py, reconciliation.py) |
| `src/rally/features/` | Yes | Directory (context_builder.py, snapshot.py) |
| `src/rally/models/` | Yes | Directory (uplift_model.py, action_ranker.py, baselines.py) |
| `src/rally/observability/` | Yes | Directory (metrics.py) |
| `src/rally/policy/` | Yes | Directory (engine.py, constraints.py) |
| `src/rally/safety/` | Yes | Directory (state_machine.py, recovery_coordinator.py, idempotency.py) |
| `src/rally/simulator/` | Yes | Directory (generator.py, error_taxonomy.py, downtime.py, models.py) |
| `frontend/` | Yes | React + Vite application |
| `tests/` | Yes | 10 test files |
| `scripts/` | Yes | 10 scripts including start_app.cmd |
| `docs/` | Yes | 4 documentation files |
| `results/` | Yes | evaluation_summary.csv, consistency_audit.txt |
| `submission/` | Yes | Buildathon submission artifacts |

## Known Placeholders

| Placeholder | Location in README | Action Required |
|---|---|---|
| Dashboard screenshot | Line 18 (HTML comment) | Replace with final screenshot |
| GitHub clone URL | "Run Locally" section | Replace `<YOUR_PUBLIC_GITHUB_URL>` with actual repo URL |
| Walkthrough video | Final line (HTML comment) | Add 5-minute video link |

## README Risk Assessment

| Check | Status |
|---|---|
| No production revenue claims | PASS |
| No "unbiased T-Learner" language | PASS |
| No stale DPL/DirectPolicyModel references | PASS |
| No oracle leakage language | PASS |
| Model honestly described as not beating baseline | PASS |
| All recovery actions match `enums.py` | PASS |
| State machine matches `RecoveryState` enum | PASS |
| Action costs match `ActionRanker.DEFAULT_ACTION_COSTS` | PASS |
| Tech versions match `pyproject.toml` requires-python | PASS |
| Test count matches actual pytest output | PASS |
| Mermaid diagram matches actual pipeline | PASS |
| Table of contents anchors use GitHub-compatible format | PASS |
