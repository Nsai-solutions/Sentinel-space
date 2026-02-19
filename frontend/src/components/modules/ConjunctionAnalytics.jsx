import { useMemo } from 'react';
import useConjunctionStore from '../../stores/conjunctionStore';
import './ConjunctionAnalytics.css';

const THREAT_COLORS = {
  CRITICAL: 'var(--threat-critical)',
  HIGH: 'var(--threat-high)',
  MODERATE: 'var(--threat-moderate)',
  LOW: 'var(--threat-low)',
};

const LEVEL_ORDER = ['CRITICAL', 'HIGH', 'MODERATE', 'LOW'];

function formatPc(pc) {
  if (!pc || pc === 0) return '0';
  return pc.toExponential(2);
}

export default function ConjunctionAnalytics() {
  const conjunctions = useConjunctionStore((s) => s.conjunctions);
  const summary = useConjunctionStore((s) => s.summary);

  const stats = useMemo(() => {
    if (conjunctions.length === 0) return null;

    const missDists = conjunctions.map((c) => c.miss_distance_m).filter((d) => d != null);
    const velocities = conjunctions.map((c) => c.relative_velocity_kms).filter((v) => v != null);
    const probs = conjunctions.map((c) => c.collision_probability).filter((p) => p != null && p > 0);

    // Per-asset breakdown
    const byAsset = {};
    conjunctions.forEach((c) => {
      const name = c.primary_asset_name || 'Unknown';
      if (!byAsset[name]) byAsset[name] = { total: 0, critical: 0, high: 0, moderate: 0, low: 0, minMiss: Infinity, maxPc: 0 };
      byAsset[name].total++;
      const lvl = (c.threat_level || 'LOW').toLowerCase();
      if (byAsset[name][lvl] != null) byAsset[name][lvl]++;
      if (c.miss_distance_m != null && c.miss_distance_m < byAsset[name].minMiss) byAsset[name].minMiss = c.miss_distance_m;
      if (c.collision_probability != null && c.collision_probability > byAsset[name].maxPc) byAsset[name].maxPc = c.collision_probability;
    });

    // By threat level
    const byLevel = {};
    LEVEL_ORDER.forEach((l) => { byLevel[l] = 0; });
    conjunctions.forEach((c) => {
      const lvl = c.threat_level || 'LOW';
      byLevel[lvl] = (byLevel[lvl] || 0) + 1;
    });

    // Miss distance histogram bins (meters)
    const histBins = [
      { label: '< 100m', min: 0, max: 100 },
      { label: '100m - 500m', min: 100, max: 500 },
      { label: '500m - 1km', min: 500, max: 1000 },
      { label: '1km - 5km', min: 1000, max: 5000 },
      { label: '5km - 10km', min: 5000, max: 10000 },
      { label: '10km - 25km', min: 10000, max: 25000 },
      { label: '> 25km', min: 25000, max: Infinity },
    ];
    const histogram = histBins.map((bin) => ({
      ...bin,
      count: missDists.filter((d) => d >= bin.min && d < bin.max).length,
    }));
    const histMax = Math.max(1, ...histogram.map((h) => h.count));

    return {
      total: conjunctions.length,
      byLevel,
      byAsset,
      missDist: {
        min: missDists.length > 0 ? Math.min(...missDists) : 0,
        max: missDists.length > 0 ? Math.max(...missDists) : 0,
        avg: missDists.length > 0 ? missDists.reduce((a, b) => a + b, 0) / missDists.length : 0,
      },
      velocity: {
        min: velocities.length > 0 ? Math.min(...velocities) : 0,
        max: velocities.length > 0 ? Math.max(...velocities) : 0,
        avg: velocities.length > 0 ? velocities.reduce((a, b) => a + b, 0) / velocities.length : 0,
      },
      maxPc: probs.length > 0 ? Math.max(...probs) : 0,
      histogram,
      histMax,
    };
  }, [conjunctions]);

  if (!stats) {
    return (
      <div className="analytics-empty">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--text-tertiary)" strokeWidth="1.5">
          <path d="M18 20V10" /><path d="M12 20V4" /><path d="M6 20v-6" />
        </svg>
        <p>No conjunction data to analyze</p>
        <p className="analytics-empty-sub">Run a screening to generate analytics</p>
      </div>
    );
  }

  return (
    <div className="conjunction-analytics">
      {/* Summary cards */}
      <div className="analytics-cards">
        <div className="analytics-card">
          <div className="analytics-card-value">{stats.total}</div>
          <div className="analytics-card-label">Total Events</div>
        </div>
        <div className="analytics-card highlight-critical">
          <div className="analytics-card-value">{stats.byLevel.CRITICAL || 0}</div>
          <div className="analytics-card-label">Critical</div>
        </div>
        <div className="analytics-card highlight-high">
          <div className="analytics-card-value">{stats.byLevel.HIGH || 0}</div>
          <div className="analytics-card-label">High</div>
        </div>
        <div className="analytics-card">
          <div className="analytics-card-value font-data">{stats.missDist.min.toFixed(0)}m</div>
          <div className="analytics-card-label">Min Miss Distance</div>
        </div>
        <div className="analytics-card">
          <div className="analytics-card-value font-data">{formatPc(stats.maxPc)}</div>
          <div className="analytics-card-label">Max Probability</div>
        </div>
        <div className="analytics-card">
          <div className="analytics-card-value font-data">{stats.velocity.avg.toFixed(2)}</div>
          <div className="analytics-card-label">Avg Rel. Vel. (km/s)</div>
        </div>
      </div>

      <div className="analytics-body">
        {/* Threat level breakdown */}
        <div className="analytics-section">
          <div className="analytics-section-title">THREAT LEVEL BREAKDOWN</div>
          <div className="threat-breakdown">
            {LEVEL_ORDER.map((level) => {
              const count = stats.byLevel[level] || 0;
              const pct = stats.total > 0 ? (count / stats.total) * 100 : 0;
              return (
                <div key={level} className="threat-bar-row">
                  <div className="threat-bar-label">
                    <span className="threat-bar-dot" style={{ background: THREAT_COLORS[level] }} />
                    {level}
                  </div>
                  <div className="threat-bar-track">
                    <div
                      className="threat-bar-fill"
                      style={{ width: `${pct}%`, background: THREAT_COLORS[level] }}
                    />
                  </div>
                  <div className="threat-bar-count font-data">{count}</div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Miss distance histogram */}
        <div className="analytics-section">
          <div className="analytics-section-title">MISS DISTANCE DISTRIBUTION</div>
          <div className="histogram">
            {stats.histogram.map((bin, i) => {
              const pct = (bin.count / stats.histMax) * 100;
              return (
                <div key={i} className="histogram-bar-row">
                  <div className="histogram-label font-data">{bin.label}</div>
                  <div className="histogram-bar-track">
                    <div
                      className="histogram-bar-fill"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <div className="histogram-count font-data">{bin.count}</div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Per-asset table */}
        <div className="analytics-section">
          <div className="analytics-section-title">PER-ASSET SUMMARY</div>
          <table className="analytics-table">
            <thead>
              <tr>
                <th>Asset</th>
                <th>Events</th>
                <th>Crit</th>
                <th>High</th>
                <th>Min Miss</th>
                <th>Max Pc</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(stats.byAsset).map(([name, data]) => (
                <tr key={name}>
                  <td>{name}</td>
                  <td className="font-data">{data.total}</td>
                  <td className="font-data" style={{ color: data.critical > 0 ? 'var(--threat-critical)' : 'inherit' }}>
                    {data.critical}
                  </td>
                  <td className="font-data" style={{ color: data.high > 0 ? 'var(--threat-high)' : 'inherit' }}>
                    {data.high}
                  </td>
                  <td className="font-data">{data.minMiss === Infinity ? '—' : `${data.minMiss.toFixed(0)}m`}</td>
                  <td className="font-data">{data.maxPc > 0 ? data.maxPc.toExponential(1) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Statistics summary */}
        <div className="analytics-section">
          <div className="analytics-section-title">ENCOUNTER STATISTICS</div>
          <div className="stats-grid">
            <div className="stat-item">
              <span className="stat-item-label">Min Miss Distance</span>
              <span className="stat-item-value font-data">{stats.missDist.min.toFixed(0)} m</span>
            </div>
            <div className="stat-item">
              <span className="stat-item-label">Max Miss Distance</span>
              <span className="stat-item-value font-data">{stats.missDist.max.toFixed(0)} m</span>
            </div>
            <div className="stat-item">
              <span className="stat-item-label">Avg Miss Distance</span>
              <span className="stat-item-value font-data">{stats.missDist.avg.toFixed(0)} m</span>
            </div>
            <div className="stat-item">
              <span className="stat-item-label">Min Rel. Velocity</span>
              <span className="stat-item-value font-data">{stats.velocity.min.toFixed(2)} km/s</span>
            </div>
            <div className="stat-item">
              <span className="stat-item-label">Max Rel. Velocity</span>
              <span className="stat-item-value font-data">{stats.velocity.max.toFixed(2)} km/s</span>
            </div>
            <div className="stat-item">
              <span className="stat-item-label">Avg Rel. Velocity</span>
              <span className="stat-item-value font-data">{stats.velocity.avg.toFixed(2)} km/s</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
