import React from 'react';
import { ArrowRight, HelpCircle } from 'lucide-react';

export default function Lifecycle() {
  return (
    <div className="page-container">
      <h2 style={{ marginBottom: '24px', fontSize: '1.5rem' }}>Payment Lifecycle State Machine</h2>
      <p style={{ color: 'var(--text-secondary)', marginBottom: '32px' }}>
        The state machine enforces deterministic transitions, ensuring actions are never executed concurrently or on terminal states.
      </p>

      <div className="card" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '48px', gap: '32px', marginBottom: '32px' }}>
        
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div style={{ padding: '12px 24px', border: '1px solid var(--border-highlight)', borderRadius: '8px' }}>IDLE</div>
          <ArrowRight />
          <div style={{ padding: '12px 24px', border: '1px solid var(--border-highlight)', borderRadius: '8px', backgroundColor: 'var(--bg-tertiary)' }}>FAILED</div>
          <ArrowRight />
          <div style={{ padding: '12px 24px', border: '1px solid var(--accent-primary)', color: 'var(--accent-primary)', borderRadius: '8px', backgroundColor: 'rgba(59, 130, 246, 0.1)' }}>RECOVERY_PENDING</div>
          <ArrowRight />
          <div style={{ padding: '12px 24px', border: '1px solid var(--border-highlight)', borderRadius: '8px' }}>RECOVERY_EXECUTING</div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginTop: '16px' }}>
          <ArrowRight style={{ transform: 'rotate(90deg)' }} />
          <div style={{ width: '400px' }}></div>
          <ArrowRight style={{ transform: 'rotate(90deg)' }} />
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '32px' }}>
          <div style={{ padding: '12px 24px', border: '1px solid var(--status-success)', color: 'var(--status-success)', borderRadius: '8px', backgroundColor: 'rgba(16, 185, 129, 0.1)' }}>RECOVERED</div>
          <div style={{ padding: '12px 24px', border: '1px solid var(--status-unknown)', color: 'var(--status-unknown)', borderRadius: '8px', backgroundColor: 'rgba(139, 92, 246, 0.1)', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <HelpCircle size={16} /> UNKNOWN
          </div>
          <div style={{ padding: '12px 24px', border: '1px solid var(--text-muted)', color: 'var(--text-muted)', borderRadius: '8px' }}>EXHAUSTED</div>
        </div>

      </div>

      <div className="card" style={{ borderLeft: '4px solid var(--status-unknown)' }}>
        <h3 className="card-title" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <HelpCircle size={20} color="var(--status-unknown)" />
          The UNKNOWN State
        </h3>
        <p style={{ marginTop: '12px', color: 'var(--text-secondary)' }}>
          UNKNOWN means the downstream execution result is not deterministic (e.g. an API timeout). Rally strictly does NOT retry or transition out of this state until a background reconciliation worker resolves the state. This absolutely prevents duplicate payments on edge cases.
        </p>
      </div>
    </div>
  );
}
