import { useEffect, useState, useRef } from 'react';
import useConjunctionStore from '../../stores/conjunctionStore';
import useAlertStore from '../../stores/alertStore';
import AlertFeed from '../modules/AlertFeed';
import NotificationSettings from '../modules/NotificationSettings';
import APIKeyManager from '../modules/APIKeyManager';
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
  const [showAlertFeed, setShowAlertFeed] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [settingsTab, setSettingsTab] = useState('notifications');
  const settingsRef = useRef(null);

  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!showSettings) return;
    const handleClick = (e) => {
      if (settingsRef.current && !settingsRef.current.contains(e.target)) {
        setShowSettings(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [showSettings]);

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

        <div className="alert-bell-wrapper" style={{ position: 'relative' }}>
          <button
            className="alert-bell"
            title="Alerts"
            onClick={() => { setShowAlertFeed(!showAlertFeed); setShowSettings(false); }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
              <path d="M13.73 21a2 2 0 0 1-3.46 0" />
            </svg>
            {unreadCount > 0 && <span className="alert-badge">{unreadCount}</span>}
          </button>
          {showAlertFeed && (
            <AlertFeed onClose={() => setShowAlertFeed(false)} />
          )}
        </div>

        <div className="settings-wrapper" ref={settingsRef}>
          <button
            className="alert-bell"
            title="Settings"
            onClick={() => { setShowSettings(!showSettings); setShowAlertFeed(false); }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
            </svg>
          </button>
          {showSettings && (
            <div className="settings-dropdown">
              <div className="settings-tabs">
                <button
                  className={`settings-tab ${settingsTab === 'notifications' ? 'active' : ''}`}
                  onClick={() => setSettingsTab('notifications')}
                >
                  Notifications
                </button>
                <button
                  className={`settings-tab ${settingsTab === 'apikeys' ? 'active' : ''}`}
                  onClick={() => setSettingsTab('apikeys')}
                >
                  API Keys
                </button>
              </div>
              <div className="settings-content">
                {settingsTab === 'notifications' && (
                  <NotificationSettings onClose={() => setShowSettings(false)} embedded />
                )}
                {settingsTab === 'apikeys' && <APIKeyManager />}
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
