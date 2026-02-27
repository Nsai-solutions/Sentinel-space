import { useEffect, useRef } from 'react';
import useAlertStore from '../../stores/alertStore';
import useConjunctionStore from '../../stores/conjunctionStore';
import './AlertFeed.css';

function timeAgo(dateStr) {
  if (!dateStr) return '';
  const now = new Date();
  const date = new Date(dateStr);
  const diffMs = now - date;
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return 'just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  return `${diffDay}d ago`;
}

export default function AlertFeed({ onClose }) {
  const alerts = useAlertStore((s) => s.alerts);
  const loading = useAlertStore((s) => s.loading);
  const loadAlerts = useAlertStore((s) => s.loadAlerts);
  const markAllRead = useAlertStore((s) => s.markAllRead);
  const selectConjunction = useConjunctionStore((s) => s.selectConjunction);
  const ref = useRef(null);

  useEffect(() => {
    loadAlerts({ limit: 50 });
  }, [loadAlerts]);

  useEffect(() => {
    const handleClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) {
        onClose();
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [onClose]);

  const handleAlertClick = (alert) => {
    if (alert.conjunction_id) {
      selectConjunction(alert.conjunction_id);
    }
    onClose();
  };

  const handleMarkAllRead = (e) => {
    e.stopPropagation();
    markAllRead();
  };

  return (
    <div className="alert-feed-dropdown" ref={ref}>
      <div className="alert-feed-header">
        <span className="alert-feed-title">Notifications</span>
        {alerts.length > 0 && (
          <button className="alert-feed-mark-read" onClick={handleMarkAllRead}>
            Mark all read
          </button>
        )}
      </div>

      <div className="alert-feed-list">
        {loading && alerts.length === 0 && (
          <div className="alert-feed-empty">Loading...</div>
        )}

        {!loading && alerts.length === 0 && (
          <div className="alert-feed-empty">
            No new alerts — run screening to detect close approaches
          </div>
        )}

        {alerts.map((alert) => {
          const level = (alert.threat_level || 'LOW').toUpperCase();
          const isUnread = alert.status === 'NEW';
          // Parse the alert message for a compact display
          // Message format: "HIGH: Conjunction with OBJECT at TCA ... - Pc=..., Miss=...m"
          const msg = alert.message || '';
          const summaryMatch = msg.match(
            /(?:CRITICAL|HIGH|MODERATE|LOW|ESCALATION):\s*(?:Conjunction with\s+)?(.+?)\s+at TCA\s+(\S+\s+\S+)\s*-\s*Pc=(\S+),\s*Miss=(\S+)/
          );

          let displayText = msg;
          let missText = '';
          if (summaryMatch) {
            const objName = summaryMatch[1];
            missText = summaryMatch[4];
            displayText = objName;
          }

          return (
            <button
              key={alert.id}
              className={`alert-feed-item ${isUnread ? 'unread' : ''}`}
              onClick={() => handleAlertClick(alert)}
            >
              <span className={`alert-feed-pill ${level.toLowerCase()}`}>
                {level}
              </span>
              <span className="alert-feed-text" title={msg}>
                {displayText}
              </span>
              {missText && (
                <span className="alert-feed-miss font-data">{missText}</span>
              )}
              <span className="alert-feed-time font-data">
                {timeAgo(alert.created_at)}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
