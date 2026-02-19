import { useEffect, useState } from 'react';
import useConjunctionStore from '../../stores/conjunctionStore';
import useAlertStore from '../../stores/alertStore';
import './TopBar.css';

const THREAT_COLORS = {
  CRITICAL: 'var(--threat-critical)',
  HIGH: 'var(--threat-high)',
  MODERATE: 'var(--threat-moderate)',
  LOW: 'var(--threat-low)',
};

export default function TopBar() {
  const summary = useConjunctionStore((s) => s.summary);
  const screening = useConjunctionStore((s) => s.screening);
  const unreadCount = useAlertStore((s) => s.unreadCount);
  const [time, setTime] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const levels = summary.by_level || {};

  return (
    <header className="topbar">
      <div className="topbar-left">
        <div className="topbar-logo">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--accent-primary)" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <ellipse cx="12" cy="12" rx="10" ry="4" transform="rotate(-30 12 12)" />
            <ellipse cx="12" cy="12" rx="10" ry="4" transform="rotate(30 12 12)" />
          </svg>
          <span className="topbar-title">SentinelSpace</span>
        </div>
      </div>

      <div className="topbar-center">
        {['CRITICAL', 'HIGH', 'MODERATE', 'LOW'].map((level) => (
          <div
            key={level}
            className={`threat-chip ${level.toLowerCase()}`}
            style={{ '--chip-color': THREAT_COLORS[level] }}
          >
            <span className="threat-chip-dot" />
            <span className="threat-chip-count">{levels[level] || 0}</span>
            <span className="threat-chip-label">{level}</span>
          </div>
        ))}
      </div>

      <div className="topbar-right">
        {screening.active && (
          <div className="scan-indicator">
            <span className="scan-dot" />
            <span>SCREENING {Math.round(screening.progress * 100)}%</span>
          </div>
        )}

        <div className="topbar-time font-data">
          {time.toISOString().slice(0, 19).replace('T', ' ')} UTC
        </div>

        <button className="alert-bell" title="Alerts">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
            <path d="M13.73 21a2 2 0 0 1-3.46 0" />
          </svg>
          {unreadCount > 0 && <span className="alert-badge">{unreadCount}</span>}
        </button>
      </div>
    </header>
  );
}
