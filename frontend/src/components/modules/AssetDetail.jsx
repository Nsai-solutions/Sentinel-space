import { useState, useEffect } from 'react';
import DataReadout from '../ui/DataReadout';
import useAssetStore from '../../stores/assetStore';
import useConjunctionStore from '../../stores/conjunctionStore';
import useUIStore from '../../stores/uiStore';
import { updateAssetConfig } from '../../api/client';
import './AssetDetail.css';

export default function AssetDetail({ data }) {
  const assets = useAssetStore((s) => s.assets);
  const startScreening = useConjunctionStore((s) => s.startScreening);
  const screening = useConjunctionStore((s) => s.screening);
  const setRightPanelMode = useUIStore((s) => s.setRightPanelMode);

  const [autoScreen, setAutoScreen] = useState(true);
  const [windowDays, setWindowDays] = useState(7);
  const [thresholdKm, setThresholdKm] = useState(25);

  useEffect(() => {
    if (data) {
      setAutoScreen(data.auto_screen ?? true);
      setWindowDays(data.screening_window_days ?? 7);
      setThresholdKm(data.screening_threshold_km ?? 25);
    }
  }, [data?.id]);

  if (!data) return null;

  const handleConfigChange = async (field, value, setter) => {
    setter(value);
    try {
      await updateAssetConfig(data.id, { [field]: value });
    } catch (err) {
      console.error('Failed to update screening config:', err);
    }
  };

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

      <div className="section-title">SCREENING SETTINGS</div>
      <div className="screening-config">
        <label className="config-row">
          <span className="config-label">Auto-Screen</span>
          <input
            type="checkbox"
            checked={autoScreen}
            onChange={(e) => handleConfigChange('auto_screen', e.target.checked, setAutoScreen)}
          />
        </label>
        <label className="config-row">
          <span className="config-label">Window</span>
          <select
            value={windowDays}
            onChange={(e) => handleConfigChange('screening_window_days', parseFloat(e.target.value), setWindowDays)}
          >
            <option value={3}>3 days</option>
            <option value={7}>7 days</option>
            <option value={14}>14 days</option>
          </select>
        </label>
        <label className="config-row">
          <span className="config-label">Threshold</span>
          <select
            value={thresholdKm}
            onChange={(e) => handleConfigChange('screening_threshold_km', parseFloat(e.target.value), setThresholdKm)}
          >
            <option value={5}>5 km</option>
            <option value={10}>10 km</option>
            <option value={25}>25 km</option>
            <option value={50}>50 km</option>
          </select>
        </label>
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
          onClick={() => {
            // Resolve fresh DB ID by NORAD ID to handle stale IDs after cold starts
            const fresh = assets.find(a => a.norad_id === data.norad_id);
            startScreening([fresh?.id || data.id]);
          }}
          disabled={screening.active}
        >
          Screen This Asset
        </button>
      </div>
    </div>
  );
}
