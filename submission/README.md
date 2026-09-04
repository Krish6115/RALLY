# Rally

**“Rally is a safe AI recovery-decision layer for failed payments. It estimates the incremental economic value of recovery actions, while deterministic policy and safety controls retain final authority over execution.”**

Razorpay AI Buildathon 2026 — Track 3: AI Revenue Recovery

> [!WARNING]
> **Audit Statement**
> Rally has not established production revenue lift. Evaluation results are based on a synthetic simulation environment. The deployable model is evaluated against an incumbent-style rule-based recovery policy and is not promoted when it underperforms.

---

## 1. Problem
When a one-time checkout payment fails, merchants typically have two blunt options: do nothing, or uniformly blast every customer with a "retry" link. These static policies fail to account for the heterogeneous nature of failures, varying customer intents, intervention costs, and the natural "self-cure" rate (customers who retry on their own without being nudged).

## 2. Solution
Rally provides an intelligent orchestration layer that sits directly on top of the payment failure webhook. It dynamically estimates the causal incremental value of each possible recovery action (`retry`, `wait`, `switch_method`, `send_link`, `escalate`, `do_nothing`) using a T-Learner uplift model. Crucially, the AI's recommendations are then strictly gated by a deterministic safety and policy engine before execution.

## 3. Architecture
The architecture strictly decouples machine learning from execution. 

```
payment.failed webhook
        │
        ▼
Live state re-check (fetch payment/order via API)
        │
        ▼
Context builder → Pre-Decision Observable Features
        │
        ▼
Candidate action generator (bounded by merchant policy)
        │
        ▼
TLearner Uplift Model → P(Recovery|Action) per arm
        │
        ▼
Economic Scorer → Ranks by Expected Net Recovered Value (ENRV)
        │
        ▼
Deterministic Safety Gate (hard constraints; vetoes unsafe ML)
        │
        ▼
Execution layer → Razorpay API Adapter
```

## 4. AI Decisioning
The core ML component is a **T-Learner Uplift Model**. Instead of simply predicting if a payment will succeed, it predicts the *conditional average treatment effect* (CATE) — the true incremental uplift of an action relative to doing nothing.

## 5. Deterministic Safety
**Core Philosophy:** "AI proposes. Deterministic controls authorize."
The system's "Governing Invariant" strictly ensures that the AI cannot accidentally trigger duplicate payments. The `RecoveryCoordinator` enforces a mandatory live-status poll against the gateway. If a payment is `captured`, `authorized`, or `refunded` — or if a concurrency race condition occurs — the safety gate deterministically aborts the ML recommendation.

## 6. Failure Recovery
The execution layer implements a strict state machine (`IDLE → FAILED → RECOVERY_EXECUTING → RECOVERED / UNKNOWN`). Edge cases like API timeouts are aggressively mapped to the `UNKNOWN` state, halting all further automated retries until a background reconciliation worker guarantees the true state.

## 7. Causal Evaluation
The system utilizes robust causal inference techniques (Doubly Robust Estimation, Inverse Propensity Scoring) to evaluate out-of-sample performance against a held-out test cohort. 

## 8. Simulation Limitations
The current implementation relies on a highly rigorous `SyntheticDataGenerator`. While mathematically complete, the observable features lack sufficient mutual information with latent ground-truth purchase intents. Consequently, the deployable model struggles to outperform the incumbent Rule-Based baseline and is actively flagged as **NOT PROMOTED**.

---

## 9. How to Run

```bash
# 1. Install dependencies
pip install -e ".[dev]"

# 2. Run the interactive frontend and backend servers
scripts\start_app.cmd
```
The React frontend will be available at `http://localhost:5173` and the FastAPI backend at `http://localhost:8000`.

## 10. Testing & Validation

```bash
# Run the complete test suite (Safety boundaries, concurrency, and uplift limits)
py -m pytest tests/ -v

# Run the master reproducibility script
py scripts/run_all_checks.py
```

## 11. Repository Structure
- `src/rally/api/` - FastAPI bindings for the frontend.
- `src/rally/safety/` - The deterministic state machine and Recovery Coordinator.
- `src/rally/policy/` - The pipeline orchestrator and constraints.
- `src/rally/models/` - T-Learner implementation and Economic Scoring.
- `src/rally/simulator/` - Data generation and latent potential outcomes.
- `frontend/` - The React/Vite UI control plane.
- `scripts/` - Utilities for causal evaluation and red-teaming.
- `tests/` - Comprehensive regression suite ensuring boundary integrity.
