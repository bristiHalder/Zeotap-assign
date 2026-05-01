import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../services/api';
import { useWebSocket } from '../hooks/useWebSocket';

function formatTime(iso) {
  if (!iso) return '--';
  return new Date(iso).toLocaleString('en-US', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [items, setItems] = useState([]);
  const [filter, setFilter] = useState({});
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  const loadData = useCallback(async () => {
    try {
      const [s, w] = await Promise.all([
        api.getDashboardStats(),
        api.listWorkItems(filter),
      ]);
      setStats(s);
      setItems(w.items || []);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  }, [filter]);

  useEffect(() => {
    loadData();
    const i = setInterval(loadData, 10000);
    return () => clearInterval(i);
  }, [loadData]);

  const onWsMessage = useCallback(
    (msg) => {
      if (msg.type === 'new_incident' || msg.type === 'state_changed') loadData();
    },
    [loadData]
  );
  const { connected } = useWebSocket(onWsMessage);

  if (loading) {
    return (
      <div className="loading-center">
        <div className="spinner" />
      </div>
    );
  }

  return (
    <>
      <div className="page-header">
        <h2>Incident Dashboard</h2>
        <p>Real-time monitoring of infrastructure incidents</p>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">Total Incidents</div>
          <div className="stat-value">{stats?.total_incidents || 0}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Active</div>
          <div className="stat-value">{stats?.active_incidents || 0}</div>
          <div className="stat-sub">Open + Investigating</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Avg MTTR</div>
          <div className="stat-value">{stats?.avg_mttr_formatted || 'N/A'}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Signals Ingested</div>
          <div className="stat-value">
            {(stats?.total_signals || 0).toLocaleString()}
          </div>
          <div className="stat-sub">
            {stats?.current_throughput?.toFixed(1) || 0} /sec
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-label">P0 Critical</div>
          <div className="stat-value" style={{ color: 'var(--severity-p0)' }}>
            {stats?.by_severity?.P0 || 0}
          </div>
        </div>
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div
          style={{
            padding: '14px 20px',
            borderBottom: '1px solid var(--border-color)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: 10,
          }}
        >
          <h3 style={{ fontSize: 15, fontWeight: 600 }}>Active Incidents</h3>
          <div className="filter-bar" style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            {['', 'OPEN', 'INVESTIGATING', 'RESOLVED', 'CLOSED'].map((s) => (
              <button
                key={s}
                className={`btn btn-sm ${filter.state === s ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() =>
                  setFilter((prev) => ({ ...prev, state: s || undefined }))
                }
              >
                {s || 'All'}
              </button>
            ))}
            <div style={{ width: 1, height: 20, background: 'var(--border-color)', margin: '0 4px' }} />
            <button 
              className="btn btn-sm btn-primary" 
              style={{ background: 'var(--accent-color)', borderColor: 'var(--accent-color)' }}
              onClick={async () => {
                const signal = {
                  component_id: `comp-${Math.floor(Math.random() * 5) + 1}`,
                  signal_type: ['CPU_HIGH', 'MEMORY_LOW', 'LATENCY_SPIKE', 'ERROR_RATE_HIGH'][Math.floor(Math.random() * 4)],
                  value: Math.floor(Math.random() * 100),
                  timestamp: new Date().toISOString(),
                  metadata: { simulated: true }
                };
                try {
                  await api.ingestSignal(signal);
                  alert(`Signal sent: ${signal.signal_type} for ${signal.component_id}`);
                  loadData();
                } catch (e) {
                  alert("Failed to send signal. Check console for details.");
                }
              }}
            >
              Simulate Signal
            </button>
          </div>
        </div>

        {items.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">--</div>
            <h3>No incidents</h3>
            <p>All systems operational</p>
          </div>
        ) : (
          <div className="table-wrapper">
            <table className="incident-table">
              <thead>
                <tr>
                  <th>Severity</th>
                  <th>Title</th>
                  <th>Component</th>
                  <th>State</th>
                  <th>Signals</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr
                    key={item.id}
                    onClick={() => navigate(`/incidents/${item.id}`)}
                  >
                    <td>
                      <span
                        className={`badge badge-${item.severity?.toLowerCase()}`}
                      >
                        {item.severity}
                      </span>
                    </td>
                    <td className="title-cell">{item.title}</td>
                    <td>
                      <span className="component-code">{item.component_id}</span>
                    </td>
                    <td>
                      <span
                        className={`badge badge-${item.state?.toLowerCase()}`}
                      >
                        {item.state}
                      </span>
                    </td>
                    <td>{item.signal_count}</td>
                    <td className="time-cell">{formatTime(item.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div
        style={{
          marginTop: 14,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          color: 'var(--text-muted)',
          fontSize: 12,
        }}
      >
        <span
          className="live-dot"
          style={{
            background: connected
              ? 'var(--success)'
              : 'var(--severity-p0)',
          }}
        />
        {connected ? 'Live updates connected' : 'Reconnecting...'}
      </div>
    </>
  );
}
