import { useState } from 'react';
import useAssetStore from '../../stores/assetStore';
import useConjunctionStore from '../../stores/conjunctionStore';
import useUIStore from '../../stores/uiStore';
import ThreatBadge from '../ui/ThreatBadge';
import './LeftPanel.css';

const THREAT_DOT_COLORS = {
  CRITICAL: 'var(--threat-critical)',
  HIGH: 'var(--threat-high)',
  MODERATE: 'var(--threat-moderate)',
  LOW: 'var(--threat-low)',
};

const PRESET_SATELLITES = [
  { norad_id: 25544, name: 'ISS (ZARYA)', orbit: 'LEO' },
  { norad_id: 20580, name: 'HUBBLE SPACE TELESCOPE', orbit: 'LEO' },
  { norad_id: 40697, name: 'SENTINEL-2A', orbit: 'SSO' },
  { norad_id: 43013, name: 'STARLINK-24', orbit: 'LEO' },
  { norad_id: 48274, name: 'STARLINK-2305', orbit: 'LEO' },
  { norad_id: 28654, name: 'NOAA 18', orbit: 'SSO' },
  { norad_id: 33591, name: 'NOAA 19', orbit: 'SSO' },
  { norad_id: 29155, name: 'GPS BIIR-13 (PRN 02)', orbit: 'MEO' },
  { norad_id: 41866, name: 'GOES 16', orbit: 'GEO' },
  { norad_id: 36516, name: 'CRYOSAT 2', orbit: 'LEO' },
  { norad_id: 44714, name: 'STARLINK-1007', orbit: 'LEO' },
  { norad_id: 27424, name: 'ENVISAT', orbit: 'SSO' },
  { norad_id: 37849, name: 'TIANGONG 2', orbit: 'LEO' },
  { norad_id: 39084, name: 'LANDSAT 8', orbit: 'SSO' },
  { norad_id: 43226, name: 'COSMOS 2251 DEB', orbit: 'LEO' },
];

export default function LeftPanel() {
  const assets = useAssetStore((s) => s.assets);
  const selectedAssetId = useAssetStore((s) => s.selectedAssetId);
  const selectAsset = useAssetStore((s) => s.selectAsset);
  const addAssetAction = useAssetStore((s) => s.addAsset);
  const removeAsset = useAssetStore((s) => s.removeAsset);
  const loadAssets = useAssetStore((s) => s.loadAssets);
  const setRightPanelMode = useUIStore((s) => s.setRightPanelMode);
  const summary = useConjunctionStore((s) => s.summary);

  const [searchQuery, setSearchQuery] = useState('');
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [addInput, setAddInput] = useState('');
  const [addLoading, setAddLoading] = useState(false);
  const [loadingPreset, setLoadingPreset] = useState(null);

  const filteredAssets = assets.filter(
    (a) => a.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
           String(a.norad_id).includes(searchQuery)
  );

  // Filter presets: hide already-added ones, filter by search input
  const existingNoradIds = new Set(assets.map((a) => a.norad_id));
  const filteredPresets = PRESET_SATELLITES.filter((p) => {
    if (existingNoradIds.has(p.norad_id)) return false;
    if (!addInput.trim()) return true;
    const q = addInput.toLowerCase();
    return p.name.toLowerCase().includes(q) || String(p.norad_id).includes(q);
  });

  const handleSelectAsset = (id) => {
    selectAsset(id);
    setRightPanelMode('asset');
  };

  const handleAddAsset = async (noradId) => {
    const id = noradId || addInput.trim();
    if (!id) return;
    const loadingKey = noradId || 'custom';
    setAddLoading(true);
    setLoadingPreset(loadingKey);
    try {
      const isNumber = /^\d+$/.test(String(id));
      await addAssetAction(
        isNumber
          ? { norad_id: parseInt(id) }
          : { name: id }
      );
      setAddInput('');
      if (!noradId) setAddDialogOpen(false);
      loadAssets();
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to add asset');
    }
    setAddLoading(false);
    setLoadingPreset(null);
  };

  const getHighestThreat = (asset) => {
    const ts = asset.threat_summary || {};
    if (ts.CRITICAL > 0) return 'CRITICAL';
    if (ts.HIGH > 0) return 'HIGH';
    if (ts.MODERATE > 0) return 'MODERATE';
    if (ts.LOW > 0) return 'LOW';
    return null;
  };

  return (
    <aside className="left-panel">
      <div className="left-panel-header">
        <h2 className="panel-title">ASSETS</h2>
        <button className="btn-add" onClick={() => setAddDialogOpen(!addDialogOpen)} title="Add satellite">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
        </button>
      </div>

      <div className="left-panel-search">
        <input
          type="text"
          placeholder="Search assets..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
      </div>

      {addDialogOpen && (
        <div className="add-asset-dialog">
          <input
            type="text"
            placeholder="NORAD ID or satellite name..."
            value={addInput}
            onChange={(e) => setAddInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleAddAsset()}
            autoFocus
          />
          {addInput.trim() && (
            <div className="add-asset-actions">
              <button className="btn-primary btn-sm" onClick={() => handleAddAsset()} disabled={addLoading}>
                {loadingPreset === 'custom' ? 'Adding...' : 'Add Custom'}
              </button>
            </div>
          )}
          <div className="preset-list">
            {filteredPresets.map((sat) => (
              <button
                key={sat.norad_id}
                className="preset-item"
                onClick={() => handleAddAsset(sat.norad_id)}
                disabled={addLoading}
              >
                <span className="preset-name">{sat.name}</span>
                <span className="preset-meta">
                  <span className="font-data">{sat.norad_id}</span>
                  <span className="preset-orbit">{sat.orbit}</span>
                </span>
                {loadingPreset === sat.norad_id && <span className="preset-loading">Adding...</span>}
              </button>
            ))}
            {filteredPresets.length === 0 && addInput.trim() && (
              <div className="preset-empty">No presets match — press Enter to add by ID/name</div>
            )}
          </div>
          <button className="btn-ghost btn-sm add-cancel" onClick={() => { setAddDialogOpen(false); setAddInput(''); }}>
            Close
          </button>
        </div>
      )}

      <div className="asset-list">
        {filteredAssets.map((asset) => {
          const threat = getHighestThreat(asset);
          return (
            <div
              key={asset.id}
              className={`asset-item ${selectedAssetId === asset.id ? 'selected' : ''}`}
              onClick={() => handleSelectAsset(asset.id)}
            >
              <div className="asset-item-dot" style={{
                background: threat ? THREAT_DOT_COLORS[threat] : 'var(--threat-none)',
              }} />
              <div className="asset-item-info">
                <div className="asset-item-name">{asset.name}</div>
                <div className="asset-item-meta">
                  <span className="font-data">{asset.norad_id}</span>
                  {asset.orbit_type && <span className="asset-orbit-type">{asset.orbit_type}</span>}
                </div>
              </div>
              {asset.active_conjunctions > 0 && (
                <span className="asset-conj-count font-data">{asset.active_conjunctions}</span>
              )}
            </div>
          );
        })}
        {filteredAssets.length === 0 && !addDialogOpen && (
          <div className="empty-state">
            No assets found
            <button className="btn-ghost btn-sm" style={{ marginTop: 8 }} onClick={() => setAddDialogOpen(true)}>
              Add satellites
            </button>
          </div>
        )}
      </div>

      <div className="left-panel-stats">
        <div className="stat-row">
          <span className="stat-label">Total Assets</span>
          <span className="stat-value font-data">{assets.length}</span>
        </div>
        <div className="stat-row">
          <span className="stat-label">Active Conjunctions</span>
          <span className="stat-value font-data">{summary.total || 0}</span>
        </div>
      </div>
    </aside>
  );
}
