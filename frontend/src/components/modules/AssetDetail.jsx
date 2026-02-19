import DataReadout from '../ui/DataReadout';
import useConjunctionStore from '../../stores/conjunctionStore';
import useUIStore from '../../stores/uiStore';
import './AssetDetail.css';

export default function AssetDetail({ data }) {
  const startScreening = useConjunctionStore((s) => s.startScreening);
  const screening = useConjunctionStore((s) => s.screening);
  const setRightPanelMode = useUIStore((s) => s.setRightPanelMode);

  if (!data) return null;

  const oe = data.orbital_elements || {};
  const tleAge = data.tle_epoch
    ? ((Date.now() - new Date(data.tle_epoch).getTime()) / 3600000).toFixed(1)
    : 'N/A';
  const tleAgeWarn = tleAge !== 'N/A' && parseFloat(tleAge) > 72;

  return (
    <div className="asset-detail">
      <div className="asset-detail-header">
        <h3 className="asset-detail-name">{data.name}</h3>
        <span className="asset-detail-norad font-data">NORAD {data.norad_id}</span>
      </div>

      {data.orbit_type && (
        <span className="asset-detail-orbit-badge">{data.orbit_type}</span>
      )}

      <div className="section-title">CURRENT STATE</div>
      <div className="readout-grid">
        <DataReadout label="Latitude" value={data.latitude?.toFixed(4) || '—'} unit="°" />
        <DataReadout label="Longitude" value={data.longitude?.toFixed(4) || '—'} unit="°" />
        <DataReadout label="Altitude" value={data.altitude_km?.toFixed(1) || '—'} unit="km" />
        <DataReadout label="Velocity" value={data.velocity_kms?.toFixed(3) || '—'} unit="km/s" />
      </div>

      <div className="section-title">ORBITAL ELEMENTS</div>
      <div className="readout-grid">
        <DataReadout label="Semi-Major Axis" value={oe.semi_major_axis_km?.toFixed(1) || '—'} unit="km" />
        <DataReadout label="Eccentricity" value={oe.eccentricity?.toFixed(6) || '—'} />
        <DataReadout label="Inclination" value={oe.inclination_deg?.toFixed(4) || '—'} unit="°" />
        <DataReadout label="RAAN" value={oe.raan_deg?.toFixed(4) || '—'} unit="°" />
        <DataReadout label="Arg Perigee" value={oe.arg_perigee_deg?.toFixed(4) || '—'} unit="°" />
        <DataReadout label="True Anomaly" value={oe.true_anomaly_deg?.toFixed(4) || '—'} unit="°" />
        <DataReadout label="Period" value={oe.period_min?.toFixed(2) || '—'} unit="min" />
        <DataReadout label="Apogee" value={oe.apogee_alt_km?.toFixed(1) || '—'} unit="km" />
        <DataReadout label="Perigee" value={oe.perigee_alt_km?.toFixed(1) || '—'} unit="km" />
      </div>

      <div className="section-title">PROPERTIES</div>
      <div className="readout-grid">
        <DataReadout label="Mass" value={data.mass_kg || '—'} unit="kg" />
        <DataReadout label="Cross-Section" value={data.cross_section_m2 || '—'} unit="m²" />
        <DataReadout label="Maneuverable" value={data.maneuverable ? 'Yes' : 'No'} />
        <DataReadout
          label="TLE Age"
          value={tleAge}
          unit="hrs"
          threat={tleAgeWarn ? 'HIGH' : undefined}
        />
      </div>

      {data.active_conjunctions > 0 && (
        <div className="asset-conjunctions-summary">
          <span className="stat-label">Active Conjunctions</span>
          <span className="stat-value font-data">{data.active_conjunctions}</span>
        </div>
      )}

      <div className="asset-detail-actions">
        <button
          className="btn-primary"
          onClick={() => startScreening([data.id])}
          disabled={screening.active}
        >
          Screen This Asset
        </button>
      </div>
    </div>
  );
}
