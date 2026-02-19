import { useMemo, useState } from 'react';
import useConjunctionStore from '../../stores/conjunctionStore';
import useUIStore from '../../stores/uiStore';
import ThreatBadge from '../ui/ThreatBadge';
import './ConjunctionTable.css';

export default function ConjunctionTable() {
  const conjunctions = useConjunctionStore((s) => s.conjunctions);
  const selectConjunction = useConjunctionStore((s) => s.selectConjunction);
  const selectedConjunctionId = useConjunctionStore((s) => s.selectedConjunctionId);
  const setRightPanelMode = useUIStore((s) => s.setRightPanelMode);
  const [assetFilter, setAssetFilter] = useState('all');

  const handleRowClick = (id) => {
    selectConjunction(id);
    setRightPanelMode('conjunction');
  };

  const formatPc = (pc) => {
    if (!pc || pc === 0) return '—';
    return pc.toExponential(2);
  };

  const formatTime = (iso) => {
    if (!iso) return '—';
    return iso.replace('T', ' ').slice(0, 19);
  };

  // Extract unique asset names for the filter dropdown
  const assetNames = useMemo(() => {
    const names = [...new Set(conjunctions.map((c) => c.primary_asset_name).filter(Boolean))];
    names.sort();
    return names;
  }, [conjunctions]);

  // Filter conjunctions by selected asset
  const filtered = useMemo(() => {
    if (assetFilter === 'all') return conjunctions;
    return conjunctions.filter((c) => c.primary_asset_name === assetFilter);
  }, [conjunctions, assetFilter]);

  return (
    <div className="conjunction-table-wrapper">
      {/* Filter bar */}
      {assetNames.length > 1 && (
        <div className="conjunction-filter-bar">
          <label className="filter-label">Asset:</label>
          <select
            className="filter-select"
            value={assetFilter}
            onChange={(e) => setAssetFilter(e.target.value)}
          >
            <option value="all">All Assets ({conjunctions.length})</option>
            {assetNames.map((name) => {
              const count = conjunctions.filter((c) => c.primary_asset_name === name).length;
              return (
                <option key={name} value={name}>
                  {name} ({count})
                </option>
              );
            })}
          </select>
        </div>
      )}

      <table className="conjunction-table">
        <thead>
          <tr>
            <th>Level</th>
            <th>Protected Asset</th>
            <th>Threat Object</th>
            <th>TCA (UTC)</th>
            <th>T-TCA</th>
            <th>Miss (m)</th>
            <th>Rel. Vel.</th>
            <th>Probability</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {filtered.length === 0 && (
            <tr>
              <td colSpan="9" className="table-empty">
                {conjunctions.length === 0
                  ? 'No conjunction events — run screening to detect close approaches'
                  : 'No conjunctions for selected asset'}
              </td>
            </tr>
          )}
          {filtered.map((c) => (
            <tr
              key={c.id}
              className={`conj-row ${c.threat_level?.toLowerCase()} ${selectedConjunctionId === c.id ? 'selected' : ''}`}
              onClick={() => handleRowClick(c.id)}
            >
              <td><ThreatBadge level={c.threat_level} small /></td>
              <td>{c.primary_asset_name}</td>
              <td>{c.secondary_name || c.secondary_norad_id}</td>
              <td className="font-data">{formatTime(c.tca)}</td>
              <td className="font-data">{c.time_to_tca_hours != null ? `${c.time_to_tca_hours.toFixed(1)}h` : '—'}</td>
              <td className="font-data">{c.miss_distance_m?.toFixed(0) || '—'}</td>
              <td className="font-data">{c.relative_velocity_kms?.toFixed(2) || '—'}</td>
              <td className="font-data">{formatPc(c.collision_probability)}</td>
              <td>{c.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
