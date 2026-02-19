import { useMemo } from 'react';
import useConjunctionStore from '../../stores/conjunctionStore';
import useUIStore from '../../stores/uiStore';
import ThreatBadge from '../ui/ThreatBadge';
import './ConjunctionTimeline.css';

const THREAT_COLORS = {
  CRITICAL: 'var(--threat-critical)',
  HIGH: 'var(--threat-high)',
  MODERATE: 'var(--threat-moderate)',
  LOW: 'var(--threat-low)',
};

const THREAT_BG = {
  CRITICAL: 'var(--threat-critical-bg)',
  HIGH: 'var(--threat-high-bg)',
  MODERATE: 'var(--threat-moderate-bg)',
  LOW: 'var(--threat-low-bg)',
};

function formatTimeTCA(hours) {
  if (hours == null) return '';
  if (hours < 1) return `${Math.round(hours * 60)}m`;
  if (hours < 24) return `${hours.toFixed(1)}h`;
  return `${(hours / 24).toFixed(1)}d`;
}

function formatDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  const mon = d.toLocaleString('en', { month: 'short' });
  return `${mon} ${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

export default function ConjunctionTimeline() {
  const conjunctions = useConjunctionStore((s) => s.conjunctions);
  const selectConjunction = useConjunctionStore((s) => s.selectConjunction);
  const selectedConjunctionId = useConjunctionStore((s) => s.selectedConjunctionId);
  const setRightPanelMode = useUIStore((s) => s.setRightPanelMode);

  // Sort by TCA time
  const sorted = useMemo(() => {
    return [...conjunctions]
      .filter((c) => c.tca)
      .sort((a, b) => new Date(a.tca) - new Date(b.tca));
  }, [conjunctions]);

  // Compute time range
  const timeRange = useMemo(() => {
    if (sorted.length === 0) return { start: Date.now(), end: Date.now() + 86400000 * 7 };
    const times = sorted.map((c) => new Date(c.tca).getTime());
    const min = Math.min(...times);
    const max = Math.max(...times);
    const pad = Math.max((max - min) * 0.1, 3600000); // at least 1h padding
    return { start: min - pad, end: max + pad };
  }, [sorted]);

  const totalSpan = timeRange.end - timeRange.start;

  // Generate time axis labels
  const axisLabels = useMemo(() => {
    const labels = [];
    const step = totalSpan / 6;
    for (let i = 0; i <= 6; i++) {
      const t = new Date(timeRange.start + step * i);
      const mon = t.toLocaleString('en', { month: 'short' });
      labels.push({
        pct: (i / 6) * 100,
        text: `${mon} ${t.getDate()} ${String(t.getHours()).padStart(2, '0')}:${String(t.getMinutes()).padStart(2, '0')}`,
      });
    }
    return labels;
  }, [timeRange, totalSpan]);

  // "Now" marker position
  const nowPct = useMemo(() => {
    const now = Date.now();
    return Math.max(0, Math.min(100, ((now - timeRange.start) / totalSpan) * 100));
  }, [timeRange, totalSpan]);

  const handleClick = (id) => {
    selectConjunction(id);
    setRightPanelMode('conjunction');
  };

  if (conjunctions.length === 0) {
    return (
      <div className="timeline-empty">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--text-tertiary)" strokeWidth="1.5">
          <circle cx="12" cy="12" r="10" />
          <polyline points="12 6 12 12 16 14" />
        </svg>
        <p>No conjunction events to display</p>
        <p className="timeline-empty-sub">Run a screening to detect close approaches</p>
      </div>
    );
  }

  return (
    <div className="conjunction-timeline">
      {/* Time axis */}
      <div className="timeline-axis">
        {axisLabels.map((l, i) => (
          <div key={i} className="timeline-axis-label font-data" style={{ left: `${l.pct}%` }}>
            <div className="timeline-axis-tick" />
            {l.text}
          </div>
        ))}
        {/* Now marker */}
        <div className="timeline-now-marker" style={{ left: `${nowPct}%` }}>
          <div className="timeline-now-line" />
          <span className="timeline-now-label font-data">NOW</span>
        </div>
      </div>

      {/* Event lanes */}
      <div className="timeline-lanes">
        {sorted.map((c) => {
          const tcaTime = new Date(c.tca).getTime();
          const pct = ((tcaTime - timeRange.start) / totalSpan) * 100;
          const level = c.threat_level || 'LOW';
          const color = THREAT_COLORS[level] || THREAT_COLORS.LOW;
          const isSelected = selectedConjunctionId === c.id;

          return (
            <div
              key={c.id}
              className={`timeline-event ${isSelected ? 'selected' : ''}`}
              onClick={() => handleClick(c.id)}
            >
              {/* Event info label */}
              <div className="timeline-event-info">
                <ThreatBadge level={level} small />
                <span className="timeline-event-name">
                  {c.primary_asset_name} vs {c.secondary_name || `#${c.secondary_norad_id}`}
                </span>
                <span className="timeline-event-meta font-data">
                  {c.miss_distance_m?.toFixed(0)}m | {c.relative_velocity_kms?.toFixed(1)} km/s
                </span>
              </div>

              {/* Timeline bar */}
              <div className="timeline-event-bar">
                <div className="timeline-bar-track">
                  {/* TCA marker */}
                  <div
                    className="timeline-tca-marker"
                    style={{ left: `${pct}%`, '--event-color': color }}
                  >
                    <div className="tca-diamond" />
                  </div>
                  {/* Uncertainty window (visual representation) */}
                  <div
                    className="timeline-uncertainty-band"
                    style={{
                      left: `${Math.max(0, pct - 2)}%`,
                      width: `${Math.min(4, 100 - pct + 2)}%`,
                      background: THREAT_BG[level],
                      borderColor: color,
                    }}
                  />
                </div>
              </div>

              {/* Time label */}
              <div className="timeline-event-time font-data">
                {formatDate(c.tca)}
                {c.time_to_tca_hours != null && (
                  <span className="timeline-ttca">T-{formatTimeTCA(c.time_to_tca_hours)}</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
