import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { getDecision } from '../api/client';
import { ArrowRight, CheckCircle2, XCircle } from 'lucide-react';

export default function DecisionExplorer() {
  const { id } = useParams();
  const [data, setData] = useState(null);

  useEffect(() => {
    getDecision(id).then(setData).catch(console.error);
  }, [id]);

  if (!data) return <div className="page-container">Loading decision details...</div>;

  return (
    <div className="page-container">
      <h2 style={{ marginBottom: '24px', fontSize: '1.5rem' }}>Decision Explorer</h2>

      <div style={{ display: 'flex', gap: '24px', marginBottom: '32px' }}>
        <div className="card" style={{ flex: 1 }}>
          <h3 className="card-title" style={{ marginBottom: '16px' }}>Payment Context</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', fontSize: '0.875rem' }}>
            <div><strong>Payment ID:</strong> {data.payment_id}</div>
            <div><strong>Amount:</strong> ₹{data.amount.toFixed(2)}</div>
            <div><strong>Method:</strong> {data.method}</div>
            <div><strong>Error Code:</strong> {data.error_code}</div>
            <div><strong>Timestamp:</strong> {new Date(data.timestamp).toLocaleString()}</div>
          </div>
        </div>
        
        <div className="card" style={{ flex: 1 }}>
          <h3 className="card-title" style={{ marginBottom: '16px', display: 'flex', justifyContent: 'space-between' }}>
            <span>Feature Snapshot</span>
            <span className="badge" style={{ backgroundColor: 'var(--border-highlight)' }}>PRE-DECISION OBSERVABLE</span>
          </h3>
          <div style={{ maxHeight: '150px', overflowY: 'auto', fontSize: '0.875rem' }}>
            {Object.entries(data.features).map(([key, val]) => (
              <div key={key} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid var(--border-subtle)' }}>
                <span style={{ color: 'var(--text-secondary)' }}>{key}</span>
                <span>{typeof val === 'number' ? val.toFixed(2) : val}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <h3 style={{ marginBottom: '16px' }}>Decision Pipeline</h3>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '32px', backgroundColor: 'var(--bg-secondary)', padding: '24px', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontWeight: '600', marginBottom: '8px' }}>FAILURE</div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{data.error_code}</div>
        </div>
        <ArrowRight color="var(--text-muted)" />
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontWeight: '600', marginBottom: '8px' }}>ML PREDICTION</div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Scores candidates</div>
        </div>
        <ArrowRight color="var(--text-muted)" />
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontWeight: '600', marginBottom: '8px' }}>ECONOMIC SCORING</div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Max ENRV: ₹{data.predicted_enrv.toFixed(2)}</div>
        </div>
        <ArrowRight color="var(--text-muted)" />
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontWeight: '600', marginBottom: '8px' }}>SAFETY CHECK</div>
          <div style={{ fontSize: '0.75rem', color: data.safety_result === 'committed' ? 'var(--status-success)' : 'var(--status-danger)' }}>
            {data.safety_result === 'committed' ? 'Authorized' : `Vetoed: ${data.veto_reason}`}
          </div>
        </div>
        <ArrowRight color="var(--text-muted)" />
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontWeight: '600', marginBottom: '8px' }}>EXECUTION</div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>State: {data.execution_state}</div>
        </div>
      </div>

      <h3 style={{ marginBottom: '16px' }}>Model Output & Economic Scoring</h3>
      <div className="card" style={{ padding: 0 }}>
        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th>Action</th>
                <th>Predicted Uplift</th>
                <th>Expected GMV</th>
                <th>Contribution</th>
                <th>Cost</th>
                <th>ENRV</th>
              </tr>
            </thead>
            <tbody>
              {data.action_rankings.map(r => (
                <tr key={r.action} style={{ backgroundColor: r.action === data.selected_action ? 'rgba(59, 130, 246, 0.1)' : 'transparent' }}>
                  <td style={{ fontWeight: r.action === data.selected_action ? '600' : 'normal', color: r.action === data.selected_action ? 'var(--accent-primary)' : 'inherit' }}>
                    {r.action}
                  </td>
                  <td>{(r.uplift * 100).toFixed(1)}%</td>
                  <td>₹{r.expected_gmv.toFixed(2)}</td>
                  <td>₹{r.expected_contribution.toFixed(2)}</td>
                  <td>₹{r.cost.toFixed(2)}</td>
                  <td style={{ fontWeight: '600' }}>₹{r.enrv.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
