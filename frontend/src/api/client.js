import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

// Assets
export const fetchAssets = () => api.get('/assets');
export const addAsset = (data) => api.post('/assets', data);
export const getAsset = (id) => api.get(`/assets/${id}`);
export const deleteAsset = (id) => api.delete(`/assets/${id}`);
export const updateAssetProperties = (id, data) => api.put(`/assets/${id}/properties`, data);

// TLE
export const fetchTLE = (noradId) => api.get(`/tle/fetch/${noradId}`);
export const uploadTLE = (text) => api.post('/tle/upload', { tle_text: text });
export const searchTLE = (q) => api.get('/tle/search', { params: { q } });
export const getCatalogStats = () => api.get('/tle/catalog/stats');
export const refreshCatalog = () => api.post('/tle/refresh');

// Screening
export const runScreening = (data) => api.post('/screening/run', data);
export const getScreeningStatus = (jobId) => api.get(`/screening/status/${jobId}`);
export const getScreeningResults = (jobId) => api.get(`/screening/results/${jobId}`);

// Conjunctions
export const fetchConjunctions = (params) => api.get('/conjunctions', { params });
export const getConjunction = (id) => api.get(`/conjunctions/${id}`);
export const getConjunctionHistory = (id) => api.get(`/conjunctions/${id}/history`);
export const runMonteCarlo = (id, n) => api.post(`/conjunctions/${id}/monte-carlo`, null, { params: { n_samples: n } });
export const acknowledgeConjunction = (id) => api.post(`/conjunctions/${id}/acknowledge`);
export const getConjunctionSummary = () => api.get('/conjunctions/summary');

// Maneuvers
export const computeManeuvers = (data) => api.post('/maneuvers/compute', data);
export const secondaryCheck = (maneuverId) => api.post('/maneuvers/secondary-check', null, { params: { maneuver_id: maneuverId } });

// Environment
export const getDebrisDensity = () => api.get('/environment/density');
export const getEnvironmentStats = () => api.get('/environment/statistics');
export const getDebrisHotspots = () => api.get('/environment/hotspots');

// Alerts
export const fetchAlerts = (params) => api.get('/alerts', { params });
export const getUnreadCount = () => api.get('/alerts/unread-count');
export const acknowledgeAlert = (id) => api.put(`/alerts/${id}/acknowledge`);
export const configureAlerts = (data) => api.post('/alerts/configure', data);

// Orbit
export const propagateSatellite = (noradId, params) => api.get(`/orbit/${noradId}/propagate`, { params });
export const getOrbitalElements = (noradId) => api.get(`/orbit/${noradId}/elements`);
export const getGroundTrack = (noradId, params) => api.get(`/orbit/${noradId}/ground-track`, { params });
export const propagateBatch = (noradIds) => api.post('/orbit/propagate-batch', noradIds);

// Reports
export const generateReport = (data) => api.post('/reports/conjunction-summary', data, { responseType: 'blob' });
export const exportConjunctions = (params) => api.get('/reports/export/conjunctions', { params, responseType: 'blob' });

export default api;
