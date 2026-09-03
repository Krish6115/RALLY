import React from 'react';
import { ShieldAlert, CheckCircle2, AlertTriangle, AlertCircle } from 'lucide-react';

export default function Safety() {
  return (
    <div className="page-container">
      <h2 style={{ marginBottom: '24px', fontSize: '1.5rem' }}>Safety & Failures</h2>
      <p style={{ color: 'var(--text-secondary)', marginBottom: '32px' }}>
        The Deterministic Safety Gate prevents the ML model from executing dangerous actions in production edge cases.
      </p>

      <h3 style={{ marginBottom: '16px' }}>Live-State Safety Guard</h3>
      <div className="card" style={{ marginBottom: '32px', borderLeft: '4px solid var(--status-danger)' }}>
        <div style={{ display: 'flex', gap: '48px' }}>
          <div>
            <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>Model Recommendation</div>
            <div style={{ fontWeight: '600', marginTop: '4px' }}>SEND_PAYMENT_LINK</div>
          </div>
          <div>
            <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>Live Payment State</div>
            <div style={{ fontWeight: '600', marginTop: '4px', color: 'var(--status-success)' }}>CAPTURED (Race Condition)</div>
          </div>
          <div>
            <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>Final Decision</div>
            <div style={{ fontWeight: '600', marginTop: '4px', color: 'var(--status-danger)' }}>ABORTED</div>
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>Reason</div>
            <div style={{ fontWeight: '600', marginTop: '4px' }}>PAYMENT_ALREADY_CAPTURED</div>
          </div>
        </div>
      </div>

      <h3 style={{ marginBottom: '16px' }}>Failure Matrix</h3>
      <div className="card" style={{ padding: 0 }}>
        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th>Scenario</th>
                <th>Expected Handling</th>
                <th>Actual Result</th>
                <th>Side Effect Prevented?</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>API Timeout</td>
                <td>Transition to UNKNOWN state</td>
                <td><span className="badge badge-warning">UNKNOWN</span></td>
                <td><CheckCircle2 size={16} color="var(--status-success)" /></td>
              </tr>
              <tr>
                <td>Duplicate Webhook</td>
                <td>Idempotency cache hit, drop duplicate</td>
                <td><span className="badge badge-success">DROPPED</span></td>
                <td><CheckCircle2 size={16} color="var(--status-success)" /></td>
              </tr>
              <tr>
                <td>Late Capture</td>
                <td>Live state check aborts recovery</td>
                <td><span className="badge badge-danger">VETOED</span></td>
                <td><CheckCircle2 size={16} color="var(--status-success)" /></td>
              </tr>
              <tr>
                <td>Concurrent Recovery</td>
                <td>Idempotency lock prevents race</td>
                <td><span className="badge badge-success">LOCKED</span></td>
                <td><CheckCircle2 size={16} color="var(--status-success)" /></td>
              </tr>
              <tr>
                <td>Stale Features</td>
                <td>Degraded fallback mode activated</td>
                <td><span className="badge badge-warning">DEGRADED</span></td>
                <td><CheckCircle2 size={16} color="var(--status-success)" /></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
