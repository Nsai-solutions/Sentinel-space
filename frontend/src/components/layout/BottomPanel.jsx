import useUIStore from '../../stores/uiStore';
import useConjunctionStore from '../../stores/conjunctionStore';
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
  const screening = useConjunctionStore((s) => s.screening);
  const startScreening = useConjunctionStore((s) => s.startScreening);

  const handleRunScreening = () => {
    startScreening([], { timeWindowDays: 7, distanceThreshold: 25 });
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
          <button
            className="btn-screen"
            onClick={handleRunScreening}
            disabled={screening.active}
          >
            {screening.active ? `Screening ${Math.round(screening.progress * 100)}%` : 'Run Screening'}
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
