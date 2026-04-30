import { useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { api } from '../services/api';

const CATEGORIES = [
  'Infrastructure',
  'Code Bug',
  'Configuration',
  'External Dependency',
  'Capacity',
  'Human Error',
  'Network',
  'Security',
  'Unknown',
];

export default function RCAForm() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    incident_start: '',
    incident_end: '',
    root_cause_category: 'Infrastructure',
    root_cause_description: '',
    fix_applied: '',
    prevention_steps: '',
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  function update(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  function calcMTTR() {
    if (!form.incident_start || !form.incident_end) return null;
    const diff =
      (new Date(form.incident_end) - new Date(form.incident_start)) / 1000;
    return diff > 0 ? diff : null;
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const data = {
        ...form,
        incident_start: new Date(form.incident_start).toISOString(),
        incident_end: new Date(form.incident_end).toISOString(),
      };
      await api.submitRCA(id, data);
      navigate(`/incidents/${id}`);
    } catch (e) {
      setError(e.message);
    }
    setLoading(false);
  }

  const mttr = calcMTTR();

  return (
    <>
      <Link to={`/incidents/${id}`} className="back-link">
        &larr; Back to Incident
      </Link>

      <div className="page-header">
        <h2>Root Cause Analysis</h2>
        <p>Work Item: {id}</p>
      </div>

      {error && (
        <div className="toast toast-error" style={{ marginBottom: 16 }}>
          {error}
        </div>
      )}

      <div className="rca-form-container" style={{ maxWidth: 700 }}>
        <form onSubmit={handleSubmit} className="card">
          <div
            className="rca-dates-grid"
            style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}
          >
            <div className="form-group">
              <label>Incident Start *</label>
              <input
                type="datetime-local"
                className="form-control"
                required
                value={form.incident_start}
                onChange={(e) => update('incident_start', e.target.value)}
              />
            </div>
            <div className="form-group">
              <label>Incident End *</label>
              <input
                type="datetime-local"
                className="form-control"
                required
                value={form.incident_end}
                onChange={(e) => update('incident_end', e.target.value)}
              />
            </div>
          </div>

          {mttr && (
            <div className="mttr-card">
              <span className="mttr-label">Calculated MTTR</span>
              <span className="mttr-value">
                {(mttr / 60).toFixed(1)} minutes ({mttr.toFixed(0)}s)
              </span>
            </div>
          )}

          <div className="form-group">
            <label>Root Cause Category *</label>
            <select
              className="form-control"
              value={form.root_cause_category}
              onChange={(e) => update('root_cause_category', e.target.value)}
            >
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label>Root Cause Description *</label>
            <textarea
              className="form-control"
              required
              placeholder="Describe the root cause of the incident..."
              value={form.root_cause_description}
              onChange={(e) => update('root_cause_description', e.target.value)}
            />
          </div>

          <div className="form-group">
            <label>Fix Applied *</label>
            <textarea
              className="form-control"
              required
              placeholder="What fix was applied to resolve the incident?"
              value={form.fix_applied}
              onChange={(e) => update('fix_applied', e.target.value)}
            />
          </div>

          <div className="form-group">
            <label>Prevention Steps *</label>
            <textarea
              className="form-control"
              required
              placeholder="What steps will prevent this from happening again?"
              value={form.prevention_steps}
              onChange={(e) => update('prevention_steps', e.target.value)}
            />
          </div>

          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={loading}
            >
              {loading ? 'Submitting...' : 'Submit RCA'}
            </button>
            <Link to={`/incidents/${id}`} className="btn btn-secondary">
              Cancel
            </Link>
          </div>
        </form>
      </div>
    </>
  );
}
