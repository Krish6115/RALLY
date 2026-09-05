import React, { useState } from 'react';
import { CheckSquare, Square, ArrowRight } from 'lucide-react';

export default function Architecture() {
  const [showDeployable, setShowDeployable] = useState(true);
  const [showSimulator, setShowSimulator] = useState(true);
  const [activeStage, setActiveStage] = useState(null);

  const deployableOpacity = showDeployable ? 1 : 0.15;
  const simulatorOpacity = showSimulator ? 1 : 0.15;

  const deployableStages = [
    {
      id: 'stage-1',
      stage: 'STAGE 01',
      title: 'Payment Failure Ingestion',
      subtitle: 'Webhook Verification & Domain Event',
      badge: 'PRODUCTION DEPLOYABLE',
      boundary: 'Deployable Core',
      description: 'Ingests Razorpay payment.failed webhooks, validates cryptographic HMAC signatures, and instantiates the bounded DomainContext.',
      inputs: 'Razorpay webhook payload, merchant API credentials',
      outputs: 'Verified PaymentFailureEvent entity',
      invariant: 'Strict idempotency key generated at boundary'
    },
    {
      id: 'stage-2',
      stage: 'STAGE 02',
      title: 'Context Builder',
      subtitle: 'Pre-Decision Observable Feature Snapshot',
      badge: 'PRODUCTION DEPLOYABLE',
      boundary: 'Feature Store',
      description: 'Extracts strictly observable attributes available prior to intervention. Strips all simulator-internal variables to prevent data leakage.',
      inputs: 'Payment method, error source, error code, past attempt history',
      outputs: 'FeatureSnapshot (strictly pre-decision observable)',
      invariant: 'Oracle labels and post-decision variables strictly prohibited'
    },
    {
      id: 'stage-3',
      stage: 'STAGE 03',
      title: 'T-Learner Uplift Model',
      subtitle: 'Causal Treatment Effect Estimation',
      badge: 'PRODUCTION DEPLOYABLE',
      boundary: 'Inference Engine',
      description: 'Evaluates candidate actions (RETRY_NOW, RETRY_ROUTED, BACKOFF_RETRY, CUSTOMER_NOTIFICATION, DO_NOTHING) against DO_NOTHING control arm to estimate incremental lift.',
      inputs: 'FeatureSnapshot, Candidate Action Set',
      outputs: 'Estimated CATE τ̂(x, a) and recovery probability P(Recovered | a)',
      invariant: 'Non-positive uplift actions deprioritized against baseline'
    },
    {
      id: 'stage-4',
      stage: 'STAGE 04',
      title: 'Economic Value Engine',
      subtitle: 'Expected Net Recovered Value (ENRV)',
      badge: 'PRODUCTION DEPLOYABLE',
      boundary: 'Decision Logic',
      description: 'Translates uplift into unit economics: ENRV = Uplift × GMV × Margin − Intervention Cost. Outputs the optimal expected-value policy action.',
      inputs: 'Estimated uplift, ticket size (GMV), merchant take-rate, channel cost',
      outputs: 'ActionRanking list, RecommendedAction with maximum ENRV',
      invariant: 'If maximum ENRV < 0, recommends DO_NOTHING'
    },
    {
      id: 'stage-5',
      stage: 'STAGE 05',
      title: 'Safety Gate & Execution',
      subtitle: 'Deterministic Policy & State Machine',
      badge: 'PRODUCTION DEPLOYABLE',
      boundary: 'Safety & Adapter',
      description: 'Validates live payment state, suppresses duplicate executions, verifies idempotency locks, and invokes Razorpay client adapter.',
      inputs: 'RecommendedAction, live payment entity state, retry counters',
      outputs: 'ExecutionResult (RECOVERED, UNKNOWN, or EXHAUSTED)',
      invariant: 'AI proposes; deterministic policy retains final veto authority'
    }
  ];

  return (
    <div className="page-container" style={{ maxWidth: '1280px', margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '24px' }}>
        <div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '6px' }}>System Architecture</h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
            Horizontal decision pipeline with strict isolation between deployable production components and offline evaluation harnesses.
          </p>
        </div>

        {/* Boundary Toggles */}
        <div style={{ display: 'flex', gap: '16px', background: 'var(--bg-secondary)', padding: '6px 14px', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
          <button 
            onClick={() => setShowDeployable(!showDeployable)}
            style={{ 
              display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.78rem', 
              background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-primary)',
              padding: '4px 6px', fontWeight: 600
            }}
            aria-label="Toggle Deployable Pipeline"
          >
            {showDeployable ? (
              <CheckSquare size={16} color="var(--accent-primary)" />
            ) : (
              <Square size={16} color="var(--border-highlight)" />
            )}
            <span style={{ opacity: showDeployable ? 1 : 0.5 }}>Deployable Pipeline</span>
          </button>

          <button 
            onClick={() => setShowSimulator(!showSimulator)}
            style={{ 
              display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.78rem', 
              background: 'none', border: 'none', cursor: 'pointer', color: 'var(--status-unknown)',
              padding: '4px 6px', fontWeight: 600
            }}
            aria-label="Toggle Simulator & Evaluator Boundary"
          >
            {showSimulator ? (
              <CheckSquare size={16} color="var(--status-unknown)" />
            ) : (
              <Square size={16} color="var(--border-highlight)" />
            )}
            <span style={{ opacity: showSimulator ? 1 : 0.5 }}>Simulator & Evaluator Boundary</span>
          </button>
        </div>
      </div>

      {/* Horizontal Pipeline Diagram Card */}
      <div className="card" style={{ padding: '24px', marginBottom: '28px', overflowX: 'auto' }}>
        <div style={{ fontSize: '0.75rem', fontWeight: 700, letterSpacing: '0.08em', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '16px' }}>
          Pipeline Flow (Horizontal Architecture)
        </div>

        {/* Upstream Simulator Block */}
        <div style={{ opacity: simulatorOpacity, transition: 'opacity 0.2s', marginBottom: '18px' }}>
          <div style={{ 
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '12px 18px', borderRadius: '6px',
            border: '1px dashed var(--status-unknown)', backgroundColor: 'rgba(139, 92, 246, 0.04)'
          }}>
            <div>
              <span style={{ fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.08em', color: 'var(--status-unknown)', padding: '2px 8px', borderRadius: '4px', backgroundColor: 'rgba(139, 92, 246, 0.15)', marginRight: '10px' }}>
                SIMULATOR
              </span>
              <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>Synthetic Payment Failure Generator</span>
              <span style={{ marginLeft: '12px', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                Simulates real-world issuer drops, gateway downtime, and card error distributions
              </span>
            </div>
            <span style={{ fontSize: '0.72rem', fontWeight: 600, color: 'var(--status-unknown)', border: '1px solid rgba(139, 92, 246, 0.3)', padding: '2px 8px', borderRadius: '4px' }}>
              OFFLINE / TESTING ONLY
            </span>
          </div>
        </div>

        {/* Deployable Horizontal Pipeline */}
        <div style={{ opacity: deployableOpacity, transition: 'opacity 0.2s' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '12px', position: 'relative' }}>
            {deployableStages.map((st, idx) => (
              <div 
                key={st.id} 
                onClick={() => setActiveStage(activeStage === st.id ? null : st.id)}
                style={{ 
                  backgroundColor: activeStage === st.id ? 'rgba(37, 99, 235, 0.08)' : 'var(--bg-secondary)',
                  border: activeStage === st.id ? '1px solid var(--accent-primary)' : '1px solid var(--border-subtle)',
                  borderRadius: '6px', padding: '14px', cursor: 'pointer',
                  display: 'flex', flexDirection: 'column', justifyContent: 'space-between',
                  minHeight: '140px', transition: 'border-color 0.2s, background-color 0.2s'
                }}
              >
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <span style={{ fontSize: '0.68rem', fontWeight: 700, letterSpacing: '0.06em', color: 'var(--accent-primary)', backgroundColor: 'rgba(37, 99, 235, 0.1)', padding: '2px 6px', borderRadius: '4px' }}>
                      {st.stage}
                    </span>
                    {idx < 4 && <ArrowRight size={14} color="var(--border-highlight)" />}
                  </div>
                  <div style={{ fontWeight: 600, fontSize: '0.88rem', marginBottom: '4px', lineHeight: 1.3 }}>
                    {st.title}
                  </div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                    {st.subtitle}
                  </div>
                </div>
                <div style={{ marginTop: '10px', paddingTop: '8px', borderTop: '1px solid var(--border-subtle)', fontSize: '0.68rem', color: 'var(--text-muted)' }}>
                  Click to inspect details
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Downstream Evaluator Block */}
        <div style={{ opacity: simulatorOpacity, transition: 'opacity 0.2s', marginTop: '18px' }}>
          <div style={{ 
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '12px 18px', borderRadius: '6px',
            border: '1px dashed var(--status-unknown)', backgroundColor: 'rgba(139, 92, 246, 0.04)'
          }}>
            <div>
              <span style={{ fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.08em', color: 'var(--status-unknown)', padding: '2px 8px', borderRadius: '4px', backgroundColor: 'rgba(139, 92, 246, 0.15)', marginRight: '10px' }}>
                EVALUATOR
              </span>
              <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>Doubly Robust Off-Policy Evaluator & Oracle Diagnostics</span>
              <span style={{ marginLeft: '12px', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                Validates causal estimates without bias; benchmarks against latent ground truth
              </span>
            </div>
            <span style={{ fontSize: '0.72rem', fontWeight: 600, color: 'var(--status-unknown)', border: '1px solid rgba(139, 92, 246, 0.3)', padding: '2px 8px', borderRadius: '4px' }}>
              OFFLINE / AUDIT ONLY
            </span>
          </div>
        </div>
      </div>

      {/* Selected Stage Detail Panel */}
      {activeStage && (
        <div className="card" style={{ marginBottom: '28px', borderLeft: '4px solid var(--accent-primary)', backgroundColor: 'rgba(37, 99, 235, 0.02)' }}>
          {(() => {
            const st = deployableStages.find(s => s.id === activeStage);
            if (!st) return null;
            return (
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--accent-primary)', backgroundColor: 'rgba(37, 99, 235, 0.1)', padding: '3px 8px', borderRadius: '4px' }}>
                      {st.stage}
                    </span>
                    <h3 style={{ fontSize: '1.1rem', fontWeight: 700 }}>{st.title}</h3>
                  </div>
                  <span style={{ fontSize: '0.72rem', fontWeight: 600, color: 'var(--status-success)', border: '1px solid rgba(16, 185, 129, 0.4)', padding: '3px 8px', borderRadius: '4px' }}>
                    {st.badge}
                  </span>
                </div>
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', marginBottom: '16px', lineHeight: 1.6 }}>
                  {st.description}
                </p>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px', fontSize: '0.8rem', backgroundColor: 'var(--bg-secondary)', padding: '14px', borderRadius: '6px', border: '1px solid var(--border-subtle)' }}>
                  <div>
                    <div style={{ fontWeight: 700, color: 'var(--text-muted)', marginBottom: '4px', textTransform: 'uppercase', fontSize: '0.68rem' }}>Inputs</div>
                    <div style={{ color: 'var(--text-primary)' }}>{st.inputs}</div>
                  </div>
                  <div>
                    <div style={{ fontWeight: 700, color: 'var(--text-muted)', marginBottom: '4px', textTransform: 'uppercase', fontSize: '0.68rem' }}>Outputs</div>
                    <div style={{ color: 'var(--text-primary)' }}>{st.outputs}</div>
                  </div>
                  <div>
                    <div style={{ fontWeight: 700, color: 'var(--text-muted)', marginBottom: '4px', textTransform: 'uppercase', fontSize: '0.68rem' }}>System Invariant</div>
                    <div style={{ color: 'var(--accent-primary)', fontWeight: 500 }}>{st.invariant}</div>
                  </div>
                </div>
              </div>
            );
          })()}
        </div>
      )}

      {/* Architectural Guarantees Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '20px' }}>
        <div className="card">
          <div style={{ fontSize: '0.72rem', fontWeight: 700, letterSpacing: '0.06em', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '8px' }}>
            PRINCIPLE 01
          </div>
          <h4 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '8px' }}>AI Proposes, Controls Authorize</h4>
          <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
            The machine learning model generates uplift and value estimates, but has zero authority to trigger external payment calls or bypass safety parameters.
          </p>
        </div>

        <div className="card">
          <div style={{ fontSize: '0.72rem', fontWeight: 700, letterSpacing: '0.06em', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '8px' }}>
            PRINCIPLE 02
          </div>
          <h4 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '8px' }}>Strict Causal Boundaries</h4>
          <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
            Context builder strictly isolates observable features. Simulator parameters, oracle ground truth, and downstream outcomes are physically excluded from inference context.
          </p>
        </div>

        <div className="card">
          <div style={{ fontSize: '0.72rem', fontWeight: 700, letterSpacing: '0.06em', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '8px' }}>
            PRINCIPLE 03
          </div>
          <h4 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '8px' }}>Deterministic State Machine</h4>
          <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
            All side effects require state transitions through verified paths. Concurrent execution is locked; timeout transitions to UNKNOWN; late capture terminates.
          </p>
        </div>
      </div>
    </div>
  );
}
