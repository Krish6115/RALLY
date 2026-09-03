import React, { useState, useEffect } from 'react';
import { getOverview } from '../api/client';
import InfoPopover from '../components/InfoPopover';

export default function Overview() {
  const [stats, setStats] = useState(null);

  const loadData = async () => {
    try {
      const data = await getOverview();
      setStats(data);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    loadData();
    window.addEventListener('simulationUpdate', loadData);
    return () => window.removeEventListener('simulationUpdate', loadData);
  }, []);

  if (!stats) return <div className="page-container">Loading overview...</div>;

  return (
    <div className="page-container">
      <div style={{ marginBottom: '32px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
          <h2 style={{ fontSize: '1.65rem', fontWeight: '700', letterSpacing: '-0.02em', color: '#0f172a' }}>
            Recovery Control Center
          </h2>
          <span className="badge" style={{ backgroundColor: '#f1f5f9', color: '#475569', border: '1px solid #cbd5e1', fontSize: '0.72rem' }}>
            SYNTHETIC COHORT
          </span>
        </div>
        <p style={{ fontSize: '1rem', color: 'var(--text-secondary)' }}>
          Real-time payment failure recovery monitoring, causal economic ranking, and deterministic safety execution.
        </p>
        <div style={{ marginTop: '16px', padding: '12px 16px', backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)', borderLeftWidth: '4px', borderLeftColor: 'var(--accent-primary)', borderRadius: '6px', fontSize: '0.875rem' }}>
          <strong style={{ color: 'var(--text-primary)' }}>Core Philosophy:</strong> AI proposes candidate recovery actions by expected net recovered value. Deterministic controls retain absolute execution authority.
        </div>
      </div>

      <div className="kpi-grid">
        <div className="card">
          <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span className="card-title">Failed Payments</span>
            <InfoPopover 
              title="Failed Payments" 
              description="Count of synthetic payment attempts that entered the failed-payment recovery flow during the current simulation." 
            />
          </div>
          <div className="kpi-value">{stats.failed_payments}</div>
          <div style={{ marginTop: '8px' }}><span className="badge badge-simulated">SYNTHETIC EVENT</span></div>
        </div>

        <div className="card">
          <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span className="card-title">Estimated ENRV</span>
            <InfoPopover 
              title="Estimated ENRV" 
              description="Expected Net Recovered Value — the estimated incremental economic value of a recovery decision after contribution margin and intervention cost." 
            />
          </div>
          <div className="kpi-value">₹{stats.estimated_enrv.toFixed(2)}</div>
          <div style={{ marginTop: '8px' }}><span className="badge badge-simulated">ESTIMATED ENRV</span></div>
        </div>

        <div className="card">
          <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span className="card-title">Safety Vetoes</span>
            <InfoPopover 
              title="Safety Vetoes" 
              description="Recovery actions blocked by deterministic safety controls, such as a captured payment, stale state, policy limits, or other execution constraints." 
            />
          </div>
          <div className="kpi-value">{stats.safety_vetoes}</div>
          <div style={{ marginTop: '8px', color: 'var(--text-secondary)', fontSize: '0.875rem' }}>Blocked by deterministic controls</div>
        </div>

        <div className="card">
          <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span className="card-title">Unknown Outcomes</span>
            <InfoPopover 
              title="Unknown Outcomes" 
              description="Recovery attempts where the downstream execution result is not yet known, typically because of a timeout or uncertain API response and requiring reconciliation." 
            />
          </div>
          <div className="kpi-value">{stats.unknown_outcomes}</div>
          <div style={{ marginTop: '8px', color: 'var(--text-secondary)', fontSize: '0.875rem' }}>Awaiting reconciliation</div>
        </div>
      </div>
    </div>
  );
}
