import React, { useState } from 'react';
import { ArrowRight, Database, Code, Shield, Network, BrainCircuit, CheckSquare, Square, Activity, BarChart3 } from 'lucide-react';

export default function Architecture() {
  const [showDeployable, setShowDeployable] = useState(true);
  const [showSimulator, setShowSimulator] = useState(true);

  const deployableOpacity = showDeployable ? 1 : 0.1;
  const simulatorOpacity = showSimulator ? 1 : 0.1;

  return (
    <div className="page-container">
      <h2 style={{ marginBottom: '24px', fontSize: '1.5rem' }}>System Architecture</h2>
      <p style={{ color: 'var(--text-secondary)', marginBottom: '32px' }}>
        Rally strictly decouples domain logic, ML estimation, and side-effect execution.
      </p>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', maxWidth: '800px', margin: '0 auto' }}>
        
        {/* Simulator Step */}
        <div className="card" style={{ display: 'flex', alignItems: 'center', gap: '24px', opacity: simulatorOpacity, transition: 'opacity 0.2s', border: '1px solid var(--status-unknown)', backgroundColor: 'rgba(139, 92, 246, 0.02)' }}>
          <Activity size={32} color="var(--status-unknown)" />
          <div>
            <h3 style={{ fontSize: '1.1rem', marginBottom: '4px', color: 'var(--status-unknown)' }}>Simulator: Synthetic Generator</h3>
            <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>Injects synthetic failures into the pipeline with latent, unobservable ground-truth outcomes for evaluation.</div>
          </div>
        </div>

        <div style={{ textAlign: 'center', color: 'var(--border-highlight)', opacity: simulatorOpacity, transition: 'opacity 0.2s' }}><ArrowRight style={{ transform: 'rotate(90deg)' }} /></div>

        {/* Step 1 */}
        <div className="card" style={{ display: 'flex', alignItems: 'center', gap: '24px', opacity: deployableOpacity, transition: 'opacity 0.2s' }}>
          <Network size={32} color="var(--accent-primary)" />
          <div>
            <h3 style={{ fontSize: '1.1rem', marginBottom: '4px' }}>1. Payment Failure (Webhook)</h3>
            <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>Razorpay webhook is verified and parsed into the bounded domain context.</div>
          </div>
        </div>

        <div style={{ textAlign: 'center', color: 'var(--border-highlight)', opacity: deployableOpacity, transition: 'opacity 0.2s' }}><ArrowRight style={{ transform: 'rotate(90deg)' }} /></div>

        {/* Step 2 */}
        <div className="card" style={{ display: 'flex', alignItems: 'center', gap: '24px', opacity: deployableOpacity, transition: 'opacity 0.2s' }}>
          <Database size={32} color="var(--text-muted)" />
          <div>
            <h3 style={{ fontSize: '1.1rem', marginBottom: '4px' }}>2. Context Builder</h3>
            <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>Extracts real-time observable features. Latent simulator variables are strictly stripped before this boundary.</div>
          </div>
        </div>

        <div style={{ textAlign: 'center', color: 'var(--border-highlight)', opacity: deployableOpacity, transition: 'opacity 0.2s' }}><ArrowRight style={{ transform: 'rotate(90deg)' }} /></div>

        {/* Step 3 */}
        <div className="card" style={{ display: 'flex', alignItems: 'center', gap: '24px', opacity: deployableOpacity, transition: 'opacity 0.2s' }}>
          <BrainCircuit size={32} color="var(--accent-secondary)" />
          <div>
            <h3 style={{ fontSize: '1.1rem', marginBottom: '4px' }}>3. T-Learner Uplift Model</h3>
            <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>Estimates the causal treatment effect of each legal action on recovery probability using only observable features.</div>
          </div>
        </div>

        <div style={{ textAlign: 'center', color: 'var(--border-highlight)', opacity: deployableOpacity, transition: 'opacity 0.2s' }}><ArrowRight style={{ transform: 'rotate(90deg)' }} /></div>

        {/* Step 4 */}
        <div className="card" style={{ display: 'flex', alignItems: 'center', gap: '24px', opacity: deployableOpacity, transition: 'opacity 0.2s' }}>
          <Code size={32} color="var(--text-primary)" />
          <div>
            <h3 style={{ fontSize: '1.1rem', marginBottom: '4px' }}>4. Economic Scorer (Action Ranker)</h3>
            <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>Translates probabilities into Expected Net Recovered Value (ENRV) subtracting intervention costs.</div>
          </div>
        </div>

        <div style={{ textAlign: 'center', color: 'var(--border-highlight)', opacity: deployableOpacity, transition: 'opacity 0.2s' }}><ArrowRight style={{ transform: 'rotate(90deg)' }} /></div>

        {/* Step 5 */}
        <div className="card" style={{ display: 'flex', alignItems: 'center', gap: '24px', border: '1px solid var(--status-success)', opacity: deployableOpacity, transition: 'opacity 0.2s' }}>
          <Shield size={32} color="var(--status-success)" />
          <div>
            <h3 style={{ fontSize: '1.1rem', marginBottom: '4px' }}>5. Recovery Coordinator (Safety Gate)</h3>
            <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>Fetches live execution state and blocks unsafe concurrent executions before dispatching to the MockRazorpayAdapter.</div>
          </div>
        </div>

        <div style={{ textAlign: 'center', color: 'var(--border-highlight)', opacity: simulatorOpacity, transition: 'opacity 0.2s' }}><ArrowRight style={{ transform: 'rotate(90deg)' }} /></div>

        {/* Evaluator Step */}
        <div className="card" style={{ display: 'flex', alignItems: 'center', gap: '24px', opacity: simulatorOpacity, transition: 'opacity 0.2s', border: '1px solid var(--status-unknown)', backgroundColor: 'rgba(139, 92, 246, 0.02)' }}>
          <BarChart3 size={32} color="var(--status-unknown)" />
          <div>
            <h3 style={{ fontSize: '1.1rem', marginBottom: '4px', color: 'var(--status-unknown)' }}>Evaluator: Oracle Policy Model</h3>
            <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>Scores the deployable pipeline against the latent, unobservable ground-truth to measure empirical regret.</div>
          </div>
        </div>

      </div>

      <div style={{ marginTop: '48px', display: 'flex', justifyContent: 'center', gap: '32px' }}>
        <button 
          onClick={() => setShowDeployable(!showDeployable)}
          style={{ 
            display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.875rem', 
            background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-primary)',
            padding: '8px', borderRadius: '4px'
          }}
          aria-label="Toggle Deployable Pipeline visibility"
        >
          {showDeployable ? (
            <CheckSquare size={18} color="var(--text-primary)" />
          ) : (
            <Square size={18} color="var(--border-highlight)" />
          )}
          <span style={{ opacity: showDeployable ? 1 : 0.6 }}>Deployable Pipeline</span>
        </button>

        <button 
          onClick={() => setShowSimulator(!showSimulator)}
          style={{ 
            display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.875rem', 
            background: 'none', border: 'none', cursor: 'pointer', color: 'var(--status-unknown)',
            padding: '8px', borderRadius: '4px'
          }}
          aria-label="Toggle Simulator & Evaluator visibility"
        >
          {showSimulator ? (
            <CheckSquare size={18} color="var(--status-unknown)" />
          ) : (
            <Square size={18} color="var(--border-highlight)" />
          )}
          <span style={{ opacity: showSimulator ? 1 : 0.6 }}>Simulator & Evaluator Only</span>
        </button>
      </div>
    </div>
  );
}
