import './ThreatBadge.css';

const COLORS = {
  CRITICAL: { bg: 'var(--threat-critical-bg)', text: 'var(--threat-critical)', border: 'rgba(255,23,68,0.3)' },
  HIGH: { bg: 'var(--threat-high-bg)', text: 'var(--threat-high)', border: 'rgba(255,109,0,0.25)' },
  MODERATE: { bg: 'var(--threat-moderate-bg)', text: 'var(--threat-moderate)', border: 'rgba(255,214,0,0.2)' },
  LOW: { bg: 'var(--threat-low-bg)', text: 'var(--threat-low)', border: 'rgba(0,230,118,0.2)' },
};

export default function ThreatBadge({ level, small = false }) {
  const style = COLORS[level] || COLORS.LOW;
  return (
    <span
      className={`threat-badge ${small ? 'small' : ''}`}
      style={{ background: style.bg, color: style.text, borderColor: style.border }}
    >
      {level}
    </span>
  );
}
