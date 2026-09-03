import React, { useState, useEffect } from 'react';
import { getFeed } from '../api/client';
import { useNavigate } from 'react-router-dom';
import { CheckCircle2, ShieldAlert, AlertTriangle, HelpCircle } from 'lucide-react';

export default function Feed() {
  const [events, setEvents] = useState([]);
  const navigate = useNavigate();

  const loadData = async () => {
    try {
      const data = await getFeed();
      setEvents(data);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    loadData();
    window.addEventListener('simulationUpdate', loadData);
    return () => window.removeEventListener('simulationUpdate', loadData);
  }, []);

  const getSeverityIcon = (event) => {
    if (event.safety_result === 'vetoed') return <ShieldAlert className="icon-danger" />;
    if (event.execution_state === 'unknown') return <HelpCircle className="icon-warning" />;
    if (event.selected_action === 'do_nothing' && event.predicted_enrv <= 0) return <AlertTriangle className="icon-warning" />;
    return <CheckCircle2 className="icon-success" />;
  };

  return (
    <div className="page-container">
      <h2 style={{ marginBottom: '24px', fontSize: '1.5rem' }}>Live Decision Feed</h2>
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        {events.length === 0 ? (
          <div style={{ padding: '48px', textAlign: 'center', color: 'var(--text-muted)' }}>
            No simulated events yet. Use the controls below to generate failures.
          </div>
        ) : (
          events.map((evt) => (
            <div key={evt.event_id} className="feed-item" onClick={() => navigate(`/decision/${evt.payment_id}`)}>
              <div className="feed-icon">{getSeverityIcon(evt)}</div>
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                  <strong>{evt.payment_id}</strong>
                  <span style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                    {new Date(evt.timestamp).toLocaleTimeString()}
                  </span>
                </div>
                <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', display: 'flex', gap: '16px' }}>
                  <span>₹{evt.amount.toFixed(2)}</span>
                  <span>{evt.method}</span>
                  <span>Error: {evt.error_code}</span>
                  <span style={{ color: evt.safety_result === 'vetoed' ? 'var(--status-danger)' : 'inherit' }}>
                    Action: {evt.selected_action}
                  </span>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
