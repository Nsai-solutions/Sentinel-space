import { useMemo } from 'react';
import './RiskGauge.css';

const THREAT_COLORS = {
  CRITICAL: '#FF1744',
  HIGH: '#FF6D00',
  MODERATE: '#FFD600',
  LOW: '#00E676',
};

function classifyPc(pc) {
  if (pc > 1e-3) return 'CRITICAL';
  if (pc > 1e-4) return 'HIGH';
  if (pc > 1e-5) return 'MODERATE';
  return 'LOW';
}

function formatPc(pc) {
  if (pc == null || pc === 0 || !isFinite(pc)) return '< 1e-15';
  const exp = Math.floor(Math.log10(Math.abs(pc)));
  const mantissa = pc / Math.pow(10, exp);
  return `${mantissa.toFixed(1)} × 10`;
}

function formatPcExp(pc) {
  if (pc == null || pc === 0 || !isFinite(pc)) return '';
  const exp = Math.floor(Math.log10(Math.abs(pc)));
  return exp.toString();
}

export default function RiskGauge({ probability, size = 120 }) {
  const level = classifyPc(probability || 0);
  const color = THREAT_COLORS[level];

  // Map probability to gauge angle (0-270 degrees)
  // Use log scale: 1e-10 = 0deg, 1e-1 = 270deg
  const logPc = probability > 0 ? Math.log10(probability) : -10;
  const normalized = Math.max(0, Math.min(1, (logPc + 10) / 9));
  const angle = normalized * 270;

  const r = size / 2 - 8;
  const cx = size / 2;
  const cy = size / 2;

  // SVG arc path
  const startAngle = 135; // degrees
  const endAngle = startAngle + angle;
  const startRad = (startAngle * Math.PI) / 180;
  const endRad = (endAngle * Math.PI) / 180;

  const x1 = cx + r * Math.cos(startRad);
  const y1 = cy + r * Math.sin(startRad);
  const x2 = cx + r * Math.cos(endRad);
  const y2 = cy + r * Math.sin(endRad);
  const largeArc = angle > 180 ? 1 : 0;

  return (
    <div className="risk-gauge" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {/* Background arc */}
        <circle
          cx={cx} cy={cy} r={r}
          fill="none"
          stroke="var(--bg-surface)"
          strokeWidth="6"
          strokeDasharray={`${(270 / 360) * 2 * Math.PI * r} ${2 * Math.PI * r}`}
          strokeDashoffset={0}
          transform={`rotate(135 ${cx} ${cy})`}
          strokeLinecap="round"
        />
        {/* Filled arc */}
        {angle > 0 && (
          <path
            d={`M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2}`}
            fill="none"
            stroke={color}
            strokeWidth="6"
            strokeLinecap="round"
            filter={`drop-shadow(0 0 4px ${color}40)`}
          />
        )}
      </svg>
      <div className="risk-gauge-text">
        <span className="risk-gauge-value" style={{ color }}>
          {formatPc(probability || 0)}
          {probability > 0 && <sup>{formatPcExp(probability)}</sup>}
        </span>
        <span className="risk-gauge-label" style={{ color }}>{level}</span>
      </div>
    </div>
  );
}
