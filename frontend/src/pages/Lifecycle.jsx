import React from 'react';
import { ArrowRight } from 'lucide-react';

export default function Lifecycle() {
  return (
    <div className="page-container" style={{ maxWidth: '1280px', margin: '0 auto' }}>
      <h2 style={{ marginBottom: '8px', fontSize: '1.5rem', fontWeight: 700 }}>Payment Lifecycle State Machine</h2>
      <p style={{ color: 'var(--text-secondary)', marginBottom: '32px', fontSize: '0.875rem' }}>
        The state machine enforces deterministic transitions, ensuring actions are never executed concurrently or on terminal states.
      </p>

      <div className="card" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '40px 24px', gap: '28px', marginBottom: '32px' }}>
        
        {/* Main Linear Transition Flow */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap', justifyContent: 'center' }}>
          <div style={{ padding: '10px 20px', border: '1px solid var(--border-highlight)', borderRadius: '6px', fontSize: '0.875rem', fontWeight: 600 }}>
            IDLE
          </div>
          <ArrowRight size={18} color="var(--border-highlight)" />
          <div style={{ padding: '10px 20px', border: '1px solid var(--border-highlight)', borderRadius: '6px', backgroundColor: 'var(--bg-tertiary)', fontSize: '0.875rem', fontWeight: 600 }}>
            FAILED
          </div>
          <ArrowRight size={18} color="var(--border-highlight)" />
          <div style={{ padding: '10px 20px', border: '1px solid var(--accent-primary)', color: 'var(--accent-primary)', borderRadius: '6px', backgroundColor: 'rgba(37, 99, 235, 0.08)', fontSize: '0.875rem', fontWeight: 600 }}>
            RECOVERY_PENDING
          </div>
          <ArrowRight size={18} color="var(--border-highlight)" />
          <div style={{ padding: '10px 20px', border: '1px solid var(--accent-primary)', color: 'var(--text-primary)', borderRadius: '6px', backgroundColor: 'var(--bg-secondary)', fontSize: '0.875rem', fontWeight: 600 }}>
            RECOVERY_EXECUTING
          </div>
        </div>

        {/* Branch Connectors */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '80px', color: 'var(--border-highlight)', width: '100%', maxWidth: '600px' }}>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Terminal Resolution Branches</span>
        </div>

        {/* Terminal Outcome States */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '20px', flexWrap: 'wrap', justifyContent: 'center' }}>
          <div style={{ padding: '10px 22px', border: '1px solid var(--status-success)', color: 'var(--status-success)', borderRadius: '6px', backgroundColor: 'rgba(16, 185, 129, 0.08)', fontSize: '0.875rem', fontWeight: 700 }}>
            RECOVERED
          </div>
          <div style={{ padding: '10px 22px', border: '1px solid var(--status-unknown)', color: 'var(--status-unknown)', borderRadius: '6px', backgroundColor: 'rgba(139, 92, 246, 0.08)', fontSize: '0.875rem', fontWeight: 700 }}>
            UNKNOWN
          </div>
          <div style={{ padding: '10px 22px', border: '1px solid var(--text-muted)', color: 'var(--text-muted)', borderRadius: '6px', backgroundColor: 'var(--bg-tertiary)', fontSize: '0.875rem', fontWeight: 600 }}>
            EXHAUSTED
          </div>
          <div style={{ padding: '10px 22px', border: '1px solid var(--status-danger)', color: 'var(--status-danger)', borderRadius: '6px', backgroundColor: 'rgba(239, 68, 68, 0.08)', fontSize: '0.875rem', fontWeight: 600 }}>
            TERMINATED
          </div>
        </div>

      </div>

      <div className="card" style={{ borderLeft: '4px solid var(--status-unknown)' }}>
        <h3 className="card-title" style={{ fontSize: '1.05rem', fontWeight: 600, color: 'var(--text-primary)' }}>
          The UNKNOWN State Architecture
        </h3>
        <p style={{ marginTop: '10px', color: 'var(--text-secondary)', fontSize: '0.875rem', lineHeight: 1.6 }}>
          UNKNOWN indicates an indeterminate downstream execution outcome (such as gateway or network API timeouts). Rally strictly prohibits autonomous retry attempts while a payment is in this state. The payment is held until background webhook reconciliation confirms the definitive state at the acquiring bank, preventing duplicate debits.
        </p>
      </div>
    </div>
  );
}
