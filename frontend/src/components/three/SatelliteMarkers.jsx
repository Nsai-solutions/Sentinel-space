import { useRef, useEffect, useMemo, useState } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { Html } from '@react-three/drei';
import useAssetStore from '../../stores/assetStore';
import { propagateBatch, propagateSatellite } from '../../api/client';

const EARTH_RADIUS_KM = 6378.137;

function latLonAltToCartesian(lat, lon, alt) {
  const phi = (90 - lat) * (Math.PI / 180);
  const theta = (lon + 180) * (Math.PI / 180);
  const r = (EARTH_RADIUS_KM + alt) / EARTH_RADIUS_KM;
  return [
    -(r * Math.sin(phi) * Math.cos(theta)),
    r * Math.cos(phi),
    r * Math.sin(phi) * Math.sin(theta),
  ];
}

export default function SatelliteMarkers() {
  const assets = useAssetStore((s) => s.assets);
  const selectedAssetId = useAssetStore((s) => s.selectedAssetId);
  const [positions, setPositions] = useState({});
  const [orbitTrail, setOrbitTrail] = useState(null);
  const pulseRef = useRef(0);

  // Fetch positions periodically
  useEffect(() => {
    if (assets.length === 0) return;

    const fetchPositions = async () => {
      const noradIds = assets.map((a) => a.norad_id);
      let posMap = {};

      // Try batch first
      try {
        const res = await propagateBatch(noradIds);
        const sats = res.data.satellites || [];
        for (const sat of sats) {
          posMap[sat.norad_id] = latLonAltToCartesian(sat.latitude, sat.longitude, sat.altitude_km);
        }
      } catch (err) {
        console.warn('Batch propagation failed, falling back to individual:', err.message);
      }

      // Fallback: fetch individually for any missing satellites
      const missing = noradIds.filter((nid) => !posMap[nid]);
      if (missing.length > 0) {
        const results = await Promise.allSettled(
          missing.map((nid) => propagateSatellite(nid, { steps: 1 }))
        );
        results.forEach((result, i) => {
          if (result.status === 'fulfilled') {
            const pts = result.value.data.points || [];
            if (pts.length > 0) {
              posMap[missing[i]] = latLonAltToCartesian(pts[0].latitude, pts[0].longitude, pts[0].altitude_km);
            }
          }
        });
      }

      if (Object.keys(posMap).length > 0) {
        setPositions(posMap);
      }
    };

    fetchPositions();
    const interval = setInterval(fetchPositions, 5000);
    return () => clearInterval(interval);
  }, [assets]);

  // Fetch orbit trail for selected asset
  useEffect(() => {
    setOrbitTrail(null);
    if (!selectedAssetId) return;

    const selectedAsset = assets.find((a) => a.id === selectedAssetId);
    if (!selectedAsset) return;

    const fetchTrail = async () => {
      try {
        // One full orbit (~90 min for LEO, 360 steps at 60s = 6 hours covers all orbit types)
        const res = await propagateSatellite(selectedAsset.norad_id, { steps: 360, step_seconds: 60 });
        const points = (res.data.points || []).map((p) =>
          latLonAltToCartesian(p.latitude, p.longitude, p.altitude_km)
        );
        if (points.length > 1) {
          setOrbitTrail(points);
        }
      } catch (err) {
        console.warn('Failed to fetch orbit trail:', err.message);
      }
    };

    fetchTrail();
  }, [selectedAssetId, assets]);

  // Animate pulse for selected satellite
  useFrame((_, delta) => {
    pulseRef.current = (pulseRef.current + delta * 2) % (Math.PI * 2);
  });

  const pulseScale = 1 + Math.sin(pulseRef.current) * 0.2;

  // Build orbit trail geometry
  const trailGeom = useMemo(() => {
    if (!orbitTrail || orbitTrail.length < 2) return null;
    const geom = new THREE.BufferGeometry();
    const pos = new Float32Array(orbitTrail.length * 3);
    for (let i = 0; i < orbitTrail.length; i++) {
      pos[i * 3] = orbitTrail[i][0];
      pos[i * 3 + 1] = orbitTrail[i][1];
      pos[i * 3 + 2] = orbitTrail[i][2];
    }
    geom.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    return geom;
  }, [orbitTrail]);

  return (
    <group>
      {/* Orbit trail for selected asset */}
      {trailGeom && (
        <line geometry={trailGeom}>
          <lineBasicMaterial color="#448AFF" transparent opacity={0.5} linewidth={1} />
        </line>
      )}

      {/* Satellite markers */}
      {assets.map((asset) => {
        const pos = positions[asset.norad_id];
        if (!pos) return null;

        const isSelected = selectedAssetId === asset.id;
        return (
          <group key={asset.id} position={pos}>
            {/* Satellite dot — larger sizes for visibility */}
            <mesh scale={isSelected ? [pulseScale, pulseScale, pulseScale] : [1, 1, 1]}>
              <sphereGeometry args={[isSelected ? 0.04 : 0.025, 16, 16]} />
              <meshBasicMaterial color={isSelected ? '#ffffff' : '#448AFF'} />
            </mesh>
            {/* Selection ring */}
            {isSelected && (
              <mesh rotation={[Math.PI / 2, 0, 0]}>
                <torusGeometry args={[0.06, 0.004, 8, 32]} />
                <meshBasicMaterial color="#448AFF" transparent opacity={0.7} />
              </mesh>
            )}
            {/* Name label for selected asset */}
            {isSelected && (
              <Html
                position={[0, 0.08, 0]}
                center
                style={{
                  color: '#ffffff',
                  fontSize: '11px',
                  fontWeight: 600,
                  background: 'rgba(6,10,19,0.8)',
                  padding: '2px 6px',
                  borderRadius: '3px',
                  whiteSpace: 'nowrap',
                  pointerEvents: 'none',
                  userSelect: 'none',
                }}
              >
                {asset.name}
              </Html>
            )}
          </group>
        );
      })}
    </group>
  );
}
