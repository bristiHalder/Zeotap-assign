import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { api } from '../services/api';

function formatTime(iso) {
  if (!iso) return '--';
  return new Date(iso).toLocaleString('en-US', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
}

const TRANSITIONS = {
  OPEN: [{ target: 'INVESTIGATING', label: 'Start Investigation', cls: 'btn-primary' }],
  INVESTIGATING: [{ target: 'RESOLVED', label: 'Mark Resolved', cls: 'btn-success' }],
  RESOLVED: [
    { target: 'CLOSED', label: 'Close (Requires RCA)', cls: 'btn-secondary' },
    { target: 'INVESTIGATING', label: 'Reopen', cls: 'btn-danger' },
  ],
  CLOSED: [],
};

export default function IncidentDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [item, setItem] = useState(null);
  const [signals, setSignals] = useState([]);
  const [transitions, setTransitions] = useState([]);
  const [rca, setRca] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionLoading, setActionLoading] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const [w, s, t] = await Promise.all([
          api.getWorkItem(id),
          api.getWorkItemSignals(id, 50),
          api.getTransitions(id),
        ]);
        setItem(w);
        setSignals(s.signals || []);
        setTransitions(t.transitions || []);
        try {
          const r = await api.getRCA(id);
          setRca(r);
        } catch {}
      } catch (e) {
        setError(e.message);
      }
      setLoading(false);
    })();
  }, [id]);

  async function handleTransition(target) {
    setActionLoading(true);
    setError('');
    try {
      await api.transitionWorkItem(id, { target_state: target });
      const w = await api.getWorkItem(id);
      setItem(w);
      const t = await api.getTransitions(id);
      setTransitions(t.transitions || []);
    } catch (e) {
      setError(e.message);
    }
    setActionLoading(false);
  }

  if (loading) {
    return (
      <div className="loading-center">
        <div className="spinner" />
      </div>
    );
  }

  if (!item) {
    return (
      <div className="empty-state">
        <h3>Incident not found</h3>
      </div>
    );
  }

  const actions = TRANSITIONS[item.state] || [];

  return (
    <>
      <Link to="/" className="back-link">
        &larr; Back to Dashboard
      </Link>

      <div className="page-header">
        <h2>{item.title}</h2>
        <p>Work Item ID: {item.id}</p>
      </div>

      {error && (
        <div className="toast toast-error" style={{ marginBottom: 16 }}>
          {error}
        </div>
      )}

      <div className="detail-grid">
        <div>
          {/* Details Card */}
          <div className="card" style={{ marginBottom: 20 }}>
            <h3 style={{ fontSize: 15, fontWeight: 600, marginBottom: 16 }}>
              Details
            </h3>
            <div className="detail-meta">
              <div className="meta-item">
                <div className="meta-label">Severity</div>
                <div className="meta-value">
                  <span className={`badge badge-${item.severity?.toLowerCase()}`}>
                    {item.severity}
                  </span>
                </div>
              </div>
              <div className="meta-item">
                <div className="meta-label">State</div>
                <div className="meta-value">
                  <span className={`badge badge-${item.state?.toLowerCase()}`}>
                    {item.state}
                  </span>
                </div>
              </div>
              <div className="meta-item">
                <div className="meta-label">Component</div>
                <div className="meta-value">
                  <span className="component-code">{item.component_id}</span>
                </div>
              </div>
              <div className="meta-item">
                <div className="meta-label">Type</div>
                <div className="meta-value">{item.component_type}</div>
              </div>
              <div className="meta-item">
                <div className="meta-label">Signals</div>
                <div className="meta-value">{item.signal_count}</div>
              </div>
              <div className="meta-item">
                <div className="meta-label">Created</div>
                <div className="meta-value" style={{ fontSize: 13 }}>
                  {formatTime(item.created_at)}
                </div>
              </div>
              {item.mttr_seconds && (
                <div className="meta-item">
                  <div className="meta-label">MTTR</div>
                  <div className="meta-value">
                    {(item.mttr_seconds / 60).toFixed(1)} min
                  </div>
                </div>
              )}
              {item.assigned_to && (
                <div className="meta-item">
                  <div className="meta-label">Assigned To</div>
                  <div className="meta-value">{item.assigned_to}</div>
                </div>
              )}
            </div>

            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {actions.map((a) => (
                <button
                  key={a.target}
                  className={`btn ${a.cls}`}
                  disabled={actionLoading}
                  onClick={() => handleTransition(a.target)}
                >
                  {a.label}
                </button>
              ))}
              {item.state === 'RESOLVED' && !rca && (
                <button
                  className="btn btn-primary"
                  onClick={() => navigate(`/incidents/${id}/rca`)}
                >
                  Submit RCA
                </button>
              )}
            </div>
          </div>

          {/* Raw Signals Card */}
          <div className="card">
            <h3 style={{ fontSize: 15, fontWeight: 600, marginBottom: 16 }}>
              Raw Signals ({signals.length})
            </h3>
            <div className="signals-table">
              <div className="table-wrapper">
                <table className="incident-table">
                  <thead>
                    <tr>
                      <th>Time</th>
                      <th>Message</th>
                      <th>Severity</th>
                    </tr>
                  </thead>
                  <tbody>
                    {signals.map((s, i) => (
                      <tr key={i} style={{ cursor: 'default' }}>
                        <td className="time-cell">{formatTime(s.timestamp)}</td>
                        <td style={{ fontSize: 13 }}>{s.message}</td>
                        <td>
                          <span
                            className={`badge badge-${s.severity?.toLowerCase()}`}
                          >
                            {s.severity}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {signals.length === 0 && (
                <div className="empty-state">
                  <p>No signals linked yet</p>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Right Sidebar */}
        <div>
          {rca && (
            <div className="card" style={{ marginBottom: 20 }}>
              <h3 style={{ fontSize: 15, fontWeight: 600, marginBottom: 16 }}>
                Root Cause Analysis
              </h3>
              <div className="form-group">
                <label>Category</label>
                <p>{rca.root_cause_category}</p>
              </div>
              <div className="form-group">
                <label>Root Cause</label>
                <p style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                  {rca.root_cause_description}
                </p>
              </div>
              <div className="form-group">
                <label>Fix Applied</label>
                <p style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                  {rca.fix_applied}
                </p>
              </div>
              <div className="form-group">
                <label>Prevention</label>
                <p style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                  {rca.prevention_steps}
                </p>
              </div>
              <div className="form-group">
                <label>MTTR</label>
                <p style={{ fontWeight: 700, color: 'var(--success)' }}>
                  {(rca.mttr_seconds / 60).toFixed(1)} minutes
                </p>
              </div>
            </div>
          )}

          <div className="card">
            <h3 style={{ fontSize: 15, fontWeight: 600, marginBottom: 16 }}>
              State Timeline
            </h3>
            {transitions.length > 0 ? (
              <div className="timeline">
                {transitions.map((t, i) => (
                  <div className="timeline-item" key={i}>
                    <div className="tl-time">{formatTime(t.transitioned_at)}</div>
                    <div className="tl-content">
                      <span className={`badge badge-${t.from_state?.toLowerCase()}`}>
                        {t.from_state}
                      </span>
                      {' \u2192 '}
                      <span className={`badge badge-${t.to_state?.toLowerCase()}`}>
                        {t.to_state}
                      </span>
                    </div>
                    {t.notes && (
                      <div
                        style={{
                          fontSize: 12,
                          color: 'var(--text-muted)',
                          marginTop: 4,
                        }}
                      >
                        {t.notes}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>
                No transitions yet
              </p>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
