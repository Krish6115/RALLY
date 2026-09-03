import React, { useState, useEffect } from 'react';
import { getEvaluation } from '../api/client';
import { ShieldAlert, Info, AlertTriangle } from 'lucide-react';

export default function Evaluation() {
  const [data, setData] = useState(null);

  useEffect(() => {
    getEvaluation().then(setData).catch(console.error);
  }, []);

  if (!data) return <div className="page-container">Loading evaluation metrics...</div>;

  return (
    <div className="page-container">
      <h2 style={{ marginBottom: '24px', fontSize: '1.5rem' }}>Out-of-Sample Evaluation</h2>
      <p style={{ color: 'var(--text-secondary)', marginBottom: '32px' }}>
        This page demonstrates our commitment to scientific honesty. The T-Learner uplift model was evaluated on a held-out synthetic cohort using the Doubly Robust estimator.
      </p>

      <div style={{ display: 'flex', gap: '24px', marginBottom: '32px' }}>
        <div className="card" style={{ flex: 1, borderLeft: data.is_promoted ? '4px solid var(--status-success)' : '4px solid var(--status-danger)' }}>
          <h3 className="card-title" style={{ marginBottom: '8px' }}>Model Promotion Status</h3>
          <div style={{ fontSize: '1.5rem', fontWeight: '700', color: data.is_promoted ? 'var(--status-success)' : 'var(--status-danger)' }}>
            {data.is_promoted ? 'PROMOTED' : 'NOT PROMOTED'}
          </div>
          <p style={{ marginTop: '12px', fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
            <strong>Reason:</strong> {data.reason}
          </p>
        </div>
        
        <div className="card" style={{ flex: 1, backgroundColor: 'rgba(245, 158, 11, 0.05)', border: '1px solid rgba(245, 158, 11, 0.2)' }}>
          <h3 className="card-title" style={{ marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--status-warning)' }}>
            <AlertTriangle size={18} /> Synthetic Environment Limitations
          </h3>
          <ul style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', marginLeft: '20px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <li>Observable features in the synthetic environment lack sufficient mutual information with latent treatment effects.</li>
            <li>Confounding remains present despite inverse propensity weighting, resulting in high variance.</li>
            <li>A more exploratory logging policy is required to safely learn causality.</li>
          </ul>
        </div>
      </div>

      <div className="card" style={{ padding: 0 }}>
        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th>Policy</th>
                <th>Ground Truth ENRV (Simulator)</th>
                <th>Doubly Robust ENRV (Estimated)</th>
                <th>95% Confidence Interval</th>
                <th>Intervention Rate</th>
              </tr>
            </thead>
            <tbody>
              {data.results.map(row => (
                <tr key={row.Policy} style={{ backgroundColor: (row.Policy === 'Rally' || row.Policy === 'PaymentPulse') ? 'rgba(59, 130, 246, 0.1)' : 'transparent' }}>
                  <td style={{ fontWeight: (row.Policy === 'Rally' || row.Policy === 'PaymentPulse') ? '600' : 'normal', color: (row.Policy === 'Rally' || row.Policy === 'PaymentPulse') ? 'var(--accent-primary)' : 'inherit' }}>
                    {row.Policy}
                  </td>
                  <td>₹{row['GT ENRV/Event'].toFixed(2)}</td>
                  <td>₹{row['DR ENRV/Event (Est)'].toFixed(2)}</td>
                  <td style={{ color: 'var(--text-secondary)' }}>{row['DR 95% CI (Est)']}</td>
                  <td>{row['Intervention Rate']}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      
      <div style={{ marginTop: '24px', padding: '16px', backgroundColor: 'var(--bg-tertiary)', borderRadius: '8px', fontSize: '0.75rem', color: 'var(--text-secondary)', display: 'flex', gap: '12px' }}>
        <Info size={16} />
        <div>
          {data.disclaimer}
        </div>
      </div>
    </div>
  );
}
