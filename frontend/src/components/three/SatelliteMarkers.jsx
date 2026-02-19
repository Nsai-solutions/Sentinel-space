import { useRef, useEffect, useMemo, useState } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import useAssetStore from '../../stores/assetStore';
import { propagateBatch } from '../../api/client';

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

  // Fetch positions periodically
  useEffect(() => {
    if (assets.length === 0) return;

    const fetchPositions = async () => {
      try {
        const noradIds = assets.map((a) => a.norad_id);
        const res = await propagateBatch(noradIds);
        const posMap = {};
        for (const sat of res.data.satellites || []) {
          posMap[sat.norad_id] = latLonAltToCartesian(sat.latitude, sat.longitude, sat.altitude_km);
        }
        setPositions(posMap);
      } catch (err) {
        // Silently fail
      }
    };

    fetchPositions();
    const interval = setInterval(fetchPositions, 5000);
    return () => clearInterval(interval);
  }, [assets]);

  return (
    <group>
      {assets.map((asset) => {
        const pos = positions[asset.norad_id];
        if (!pos) return null;

        const isSelected = selectedAssetId === asset.id;
        return (
          <group key={asset.id} position={pos}>
            {/* Satellite dot */}
            <mesh>
              <sphereGeometry args={[isSelected ? 0.025 : 0.015, 12, 12]} />
              <meshBasicMaterial color={isSelected ? '#ffffff' : '#448AFF'} />
            </mesh>
            {/* Selection ring */}
            {isSelected && (
              <mesh rotation={[Math.PI / 2, 0, 0]}>
                <torusGeometry args={[0.04, 0.003, 8, 32]} />
                <meshBasicMaterial color="#448AFF" />
              </mesh>
            )}
          </group>
        );
      })}
    </group>
  );
}
