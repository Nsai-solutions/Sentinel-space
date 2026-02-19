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
    if (pc == null) return '—';
    if (pc === 0) return '< 1e-15';
    if (pc < 1e-12) return `${pc.toExponential(1)}`;
    return pc.toExponential(2);
  };

  const formatDist = (val) => {
    if (val == null) return '—';
    if (Math.abs(val) >= 1000) return `${(val / 1000).toFixed(2)} km`;
    return `${val.toFixed(1)} m`;
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

  // Handle both flat (list endpoint) and nested (detail endpoint) structures
  const primaryName = data.primary?.name || data.primary_asset_name || 'Unknown';
  const primaryNorad = data.primary?.norad_id || data.primary_norad_id || 0;
  const secondaryName = data.secondary?.name || data.secondary_name || `NORAD ${data.secondary?.norad_id || data.secondary_norad_id}`;
  const secondaryNorad = data.secondary?.norad_id || data.secondary_norad_id || 0;
  const secondaryType = data.secondary?.object_type || data.secondary_object_type;
  const isManeuverable = data.primary?.maneuverable;

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
          <div className="object-card-name">{primaryName}</div>
          <div className="object-card-meta font-data">NORAD {primaryNorad}</div>
          {isManeuverable && <span className="maneuver-badge">Maneuverable</span>}
        </div>
        <div className="vs-divider">VS</div>
        <div className="object-card threat">
          <div className="object-card-title">THREAT</div>
          <div className="object-card-name">{secondaryName}</div>
          <div className="object-card-meta font-data">NORAD {secondaryNorad}</div>
          {secondaryType && <span className="type-badge">{secondaryType}</span>}
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
          value={formatDist(data.miss_distance_m)}
          threat={data.threat_level}
        />
        <DataReadout label="Relative Velocity" value={data.relative_velocity_kms?.toFixed(3) || '—'} unit="km/s" />
        <DataReadout label="Radial" value={data.radial_m != null ? `${data.radial_m.toFixed(1)}` : '—'} unit="m" />
        <DataReadout label="In-Track" value={data.in_track_m != null ? `${data.in_track_m.toFixed(1)}` : '—'} unit="m" />
        <DataReadout label="Cross-Track" value={data.cross_track_m != null ? `${data.cross_track_m.toFixed(1)}` : '—'} unit="m" />
        <DataReadout label="Probability" value={formatPc(data.collision_probability)} threat={data.threat_level} />
      </div>

      {/* Combined hard body radius */}
      {data.combined_hard_body_radius_m && (
        <div className="readout-grid" style={{ marginTop: 4 }}>
          <DataReadout label="Combined HBR" value={data.combined_hard_body_radius_m.toFixed(2)} unit="m" />
        </div>
      )}

      {/* Uncertainty */}
      {data.uncertainty && (
        <>
          <div className="section-title">UNCERTAINTY (1 sigma)</div>
          <div className="readout-grid">
            <DataReadout label="Prim. Radial" value={data.uncertainty.primary_sigma_radial_m?.toFixed(0) || '—'} unit="m" />
            <DataReadout label="Prim. In-Track" value={data.uncertainty.primary_sigma_in_track_m?.toFixed(0) || '—'} unit="m" />
            <DataReadout label="Prim. Cross-Trk" value={data.uncertainty.primary_sigma_cross_track_m?.toFixed(0) || '—'} unit="m" />
            <DataReadout label="Sec. Radial" value={data.uncertainty.secondary_sigma_radial_m?.toFixed(0) || '—'} unit="m" />
            <DataReadout label="Sec. In-Track" value={data.uncertainty.secondary_sigma_in_track_m?.toFixed(0) || '—'} unit="m" />
            <DataReadout label="Sec. Cross-Trk" value={data.uncertainty.secondary_sigma_cross_track_m?.toFixed(0) || '—'} unit="m" />
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
                <th>dv (m/s)</th>
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
