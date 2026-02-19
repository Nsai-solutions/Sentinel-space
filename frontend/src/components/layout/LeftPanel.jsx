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

  const filteredAssets = assets.filter(
    (a) => a.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
           String(a.norad_id).includes(searchQuery)
  );

  const handleSelectAsset = (id) => {
    selectAsset(id);
    setRightPanelMode('asset');
  };

  const handleAddAsset = async () => {
    if (!addInput.trim()) return;
    setAddLoading(true);
    try {
      const isNumber = /^\d+$/.test(addInput.trim());
      await addAssetAction(
        isNumber
          ? { norad_id: parseInt(addInput.trim()) }
          : { name: addInput.trim() }
      );
      setAddInput('');
      setAddDialogOpen(false);
      loadAssets();
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to add asset');
    }
    setAddLoading(false);
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
        <button className="btn-add" onClick={() => setAddDialogOpen(true)} title="Add satellite">
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
            placeholder="NORAD ID or name..."
            value={addInput}
            onChange={(e) => setAddInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleAddAsset()}
            autoFocus
          />
          <div className="add-asset-actions">
            <button className="btn-primary btn-sm" onClick={handleAddAsset} disabled={addLoading}>
              {addLoading ? 'Adding...' : 'Add'}
            </button>
            <button className="btn-ghost btn-sm" onClick={() => setAddDialogOpen(false)}>Cancel</button>
          </div>
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
        {filteredAssets.length === 0 && (
          <div className="empty-state">No assets found</div>
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
