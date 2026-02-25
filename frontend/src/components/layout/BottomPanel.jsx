import { useState, useRef, useEffect } from 'react';
import useUIStore from '../../stores/uiStore';
import useAssetStore from '../../stores/assetStore';
import useConjunctionStore from '../../stores/conjunctionStore';
import { exportConjunctions } from '../../api/client';
import ConjunctionTable from '../modules/ConjunctionTable';
import ConjunctionTimeline from '../modules/ConjunctionTimeline';
import ConjunctionAnalytics from '../modules/ConjunctionAnalytics';
import './BottomPanel.css';

const TABS = [
  { id: 'table', label: 'Event Table' },
  { id: 'timeline', label: 'Timeline' },
  { id: 'analytics', label: 'Analytics' },
];

export default function BottomPanel({ expanded }) {
  const activeTab = useUIStore((s) => s.bottomPanelTab);
  const setTab = useUIStore((s) => s.setBottomPanelTab);
  const togglePanel = useUIStore((s) => s.toggleBottomPanel);
  const assets = useAssetStore((s) => s.assets);
  const selectedAssetId = useAssetStore((s) => s.selectedAssetId);
  const screening = useConjunctionStore((s) => s.screening);
  const startScreening = useConjunctionStore((s) => s.startScreening);
  const clearAllConjunctions = useConjunctionStore((s) => s.clearAllConjunctions);
  const [showExport, setShowExport] = useState(false);
  const exportRef = useRef(null);

  useEffect(() => {
    if (!showExport) return;
    const handleClick = (e) => {
      if (exportRef.current && !exportRef.current.contains(e.target)) {
        setShowExport(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [showExport]);

  const handleExport = async (format) => {
    setShowExport(false);
    try {
      const params = { format };
      if (selectedAssetId) params.asset_id = selectedAssetId;
      const res = await exportConjunctions(params);
      const ext = format === 'csv' ? 'csv' : 'json';
      const blob = new Blob([res.data], { type: format === 'csv' ? 'text/csv' : 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `conjunctions.${ext}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Export failed:', err);
    }
  };

  const handleRunScreening = () => {
    if (selectedAssetId) {
      startScreening([selectedAssetId], { timeWindowDays: 7, distanceThreshold: 25 });
    } else {
      const ids = assets.map((a) => a.id);
      startScreening(ids, { timeWindowDays: 7, distanceThreshold: 25 });
    }
  };

  const statusClass = screening.status === 'FAILED' ? 'error'
    : screening.status === 'COMPLETED' ? 'complete' : '';

  return (
    <div className={`bottom-panel ${expanded ? 'expanded' : 'collapsed'}`}>
      <div className="bottom-panel-header">
        <div className="bottom-panel-tabs">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              className={`bottom-tab ${activeTab === tab.id ? 'active' : ''}`}
              onClick={() => { setTab(tab.id); if (!expanded) togglePanel(); }}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <div className="bottom-panel-actions">
          {screening.statusText && (
            <div className={`screening-status ${statusClass}`}>
              {screening.active && (
                <div className="screening-progress-bar">
                  <div
                    className="screening-progress-fill"
                    style={{ width: `${Math.round(screening.progress * 100)}%` }}
                  />
                </div>
              )}
              <span className="screening-status-text">{screening.statusText}</span>
            </div>
          )}
          {screening.statusText && !screening.active && (
            <button
              className="btn-clear"
              onClick={clearAllConjunctions}
              title="Clear screening results"
            >
              Clear
            </button>
          )}
          <div className="export-wrapper" ref={exportRef}>
            <button
              className="btn-clear"
              onClick={() => setShowExport(!showExport)}
              title="Export conjunction data"
            >
              Export
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ marginLeft: 4 }}>
                <polyline points="6 9 12 15 18 9" />
              </svg>
            </button>
            {showExport && (
              <div className="export-dropdown">
                <button className="export-option" onClick={() => handleExport('csv')}>
                  Export CSV
                </button>
                <button className="export-option" onClick={() => handleExport('json')}>
                  Export JSON
                </button>
              </div>
            )}
          </div>
          <button
            className="btn-screen"
            onClick={handleRunScreening}
            disabled={screening.active || assets.length === 0}
          >
            {screening.active
              ? `Screening ${Math.round(screening.progress * 100)}%`
              : selectedAssetId
                ? 'Screen Selected'
                : 'Screen All Assets'}
          </button>
          <button className="btn-toggle" onClick={togglePanel}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
              style={{ transform: expanded ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}>
              <polyline points="18 15 12 9 6 15" />
            </svg>
          </button>
        </div>
      </div>

      {expanded && (
        <div className="bottom-panel-content">
          {activeTab === 'table' && <ConjunctionTable />}
          {activeTab === 'timeline' && <ConjunctionTimeline />}
          {activeTab === 'analytics' && <ConjunctionAnalytics />}
        </div>
      )}
    </div>
  );
}
