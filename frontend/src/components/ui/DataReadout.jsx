import './DataReadout.css';

export default function DataReadout({ label, value, unit, threat }) {
  return (
    <div className="readout-cell">
      <div className="readout-label">{label}</div>
      <div className={`readout-value ${threat ? threat.toLowerCase() : ''}`}>
        {value}
        {unit && <span className="readout-unit">{unit}</span>}
      </div>
    </div>
  );
}
