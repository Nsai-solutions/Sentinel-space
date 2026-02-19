import { useState } from 'react';
import DataReadout from '../ui/DataReadout';
import ThreatBadge from '../ui/ThreatBadge';
import RiskGauge from '../ui/RiskGauge';
import { computeManeuvers } from '../../api/client';
import './ConjunctionDetail.css';

export default function ConjunctionDetail({ data }) {
  const [maneuverOptions, setManeuverOptions] = useState(data.maneuver_options || []);
  const [computing, setComputing] = useState(false);

  if (!data) return null;

  const formatPc = (pc) => {
    if (!pc || pc === 0) return '0';
    return pc.toExponential(2);
  };

  const handleComputeManeuvers = async () => {
    setComputing(true);
    try {
      const res = await computeManeuvers({ conjunction_id: data.id });
      setManeuverOptions(res.data);
    } catch (err) {
      console.error('Maneuver computation failed:', err);
    }
    setComputing(false);
  };

  return (
    <div className="conjunction-detail">
      <div className="conjunction-detail-header">
        <ThreatBadge level={data.threat_level} />
        <span className="conjunction-detail-id font-data">Event #{data.id}</span>
      </div>

      {/* Object comparison */}
      <div className="object-comparison">
        <div className="object-card">
          <div className="object-card-title">PROTECTED</div>
          <div className="object-card-name">{data.primary?.name}</div>
          <div className="object-card-meta font-data">NORAD {data.primary?.norad_id}</div>
          {data.primary?.maneuverable && <span className="maneuver-badge">Maneuverable</span>}
        </div>
        <div className="vs-divider">VS</div>
        <div className="object-card threat">
          <div className="object-card-title">THREAT</div>
          <div className="object-card-name">{data.secondary?.name || `NORAD ${data.secondary?.norad_id}`}</div>
          <div className="object-card-meta font-data">NORAD {data.secondary?.norad_id}</div>
          {data.secondary?.object_type && <span className="type-badge">{data.secondary.object_type}</span>}
        </div>
      </div>

      {/* Risk gauge */}
      <div className="risk-section">
        <RiskGauge probability={data.collision_probability} size={140} />
      </div>

      {/* TCA */}
      <div className="tca-section">
        <div className="tca-label">TIME OF CLOSEST APPROACH</div>
        <div className="tca-value font-data">{data.tca?.replace('T', ' ').slice(0, 19)} UTC</div>
        {data.time_to_tca_hours != null && (
          <div className="tca-countdown font-data">
            T-{data.time_to_tca_hours.toFixed(1)} hours
          </div>
        )}
      </div>

      {/* Miss distance breakdown */}
      <div className="section-title">MISS DISTANCE</div>
      <div className="readout-grid">
        <DataReadout
          label="Total"
          value={data.miss_distance_m?.toFixed(1) || '—'}
          unit="m"
          threat={data.threat_level}
        />
        <DataReadout label="Relative Velocity" value={data.relative_velocity_kms?.toFixed(3) || '—'} unit="km/s" />
        <DataReadout label="Radial" value={data.radial_m?.toFixed(1) || '—'} unit="m" />
        <DataReadout label="In-Track" value={data.in_track_m?.toFixed(1) || '—'} unit="m" />
        <DataReadout label="Cross-Track" value={data.cross_track_m?.toFixed(1) || '—'} unit="m" />
        <DataReadout label="Probability" value={formatPc(data.collision_probability)} threat={data.threat_level} />
      </div>

      {/* Uncertainty */}
      {data.uncertainty && (
        <>
          <div className="section-title">UNCERTAINTY (1σ)</div>
          <div className="readout-grid">
            <DataReadout label="Prim. Radial" value={data.uncertainty.primary_sigma_radial_m?.toFixed(0) || '—'} unit="m" />
            <DataReadout label="Prim. In-Track" value={data.uncertainty.primary_sigma_in_track_m?.toFixed(0) || '—'} unit="m" />
            <DataReadout label="Sec. Radial" value={data.uncertainty.secondary_sigma_radial_m?.toFixed(0) || '—'} unit="m" />
            <DataReadout label="Sec. In-Track" value={data.uncertainty.secondary_sigma_in_track_m?.toFixed(0) || '—'} unit="m" />
          </div>
        </>
      )}

      {/* Maneuver section */}
      <div className="section-title">AVOIDANCE MANEUVERS</div>
      {maneuverOptions.length > 0 ? (
        <div className="maneuver-table">
          <table>
            <thead>
              <tr>
                <th>Opt</th>
                <th>Direction</th>
                <th>Δv (m/s)</th>
                <th>New Miss (m)</th>
                <th>New Pc</th>
              </tr>
            </thead>
            <tbody>
              {maneuverOptions.map((opt) => (
                <tr key={opt.id || opt.label}>
                  <td className="font-data">{opt.label}</td>
                  <td>{opt.direction}</td>
                  <td className="font-data">{opt.delta_v_ms?.toFixed(4)}</td>
                  <td className="font-data">{opt.new_miss_distance_m?.toFixed(0)}</td>
                  <td className="font-data">{opt.new_collision_probability?.toExponential(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <button
          className="btn-primary"
          style={{ width: '100%', marginTop: 4 }}
          onClick={handleComputeManeuvers}
          disabled={computing}
        >
          {computing ? 'Computing...' : 'Compute Avoidance Options'}
        </button>
      )}
    </div>
  );
}
