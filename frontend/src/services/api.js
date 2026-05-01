const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Request failed');
  }
  return res.json();
}

export const api = {
  getHealth: () => request('/health'),
  getDashboardStats: () => request('/api/v1/dashboard/stats'),
  getTimeseries: (metric = 'signals_per_sec', mins = 60) =>
    request(`/api/v1/dashboard/timeseries?metric=${metric}&duration_minutes=${mins}`),
  listWorkItems: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return request(`/api/v1/workitems/${q ? '?' + q : ''}`);
  },
  getWorkItem: (id) => request(`/api/v1/workitems/${id}`),
  getWorkItemSignals: (id, limit = 100) =>
    request(`/api/v1/workitems/${id}/signals?limit=${limit}`),
  transitionWorkItem: (id, data) =>
    request(`/api/v1/workitems/${id}/transition`, { method: 'PATCH', body: JSON.stringify(data) }),
  getTransitions: (id) => request(`/api/v1/workitems/${id}/transitions`),
  submitRCA: (id, data) =>
    request(`/api/v1/workitems/${id}/rca`, { method: 'POST', body: JSON.stringify(data) }),
  getRCA: (id) => request(`/api/v1/workitems/${id}/rca`),
  ingestSignal: (data) =>
    request('/api/v1/signals', { method: 'POST', body: JSON.stringify(data) }),
};

export function createWebSocket() {
  const wsUrl = API_BASE.replace(/^http/, 'ws') + '/api/v1/ws';
  return new WebSocket(wsUrl);
}
