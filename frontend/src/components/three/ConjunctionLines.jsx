import { useRef, useEffect, useState, useMemo } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';
import useConjunctionStore from '../../stores/conjunctionStore';
import { propagateSatellite } from '../../api/client';

const EARTH_RADIUS_KM = 6378.137;

const THREAT_COLORS = {
  CRITICAL: '#FF1744',
  HIGH: '#FF6D00',
  MODERATE: '#FFD600',
  LOW: '#00E676',
};

function eciToScene(posEci) {
  // ECI km → scene units (normalized to Earth radius)
  // Three.js: x=right, y=up, z=towards camera
  // ECI: x=vernal equinox, y=90°, z=north pole
  return [
    posEci[0] / EARTH_RADIUS_KM,
    posEci[2] / EARTH_RADIUS_KM,  // ECI Z → scene Y (up)
    -posEci[1] / EARTH_RADIUS_KM, // ECI Y → scene -Z
  ];
}

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

export default function ConjunctionLines() {
  const selectedConjunction = useConjunctionStore((s) => s.selectedConjunction);
  const conjunctions = useConjunctionStore((s) => s.conjunctions);

  const [primaryTrail, setPrimaryTrail] = useState(null);
  const [secondaryTrail, setSecondaryTrail] = useState(null);
  const [tcaPositions, setTcaPositions] = useState(null);
  const [debrisPositions, setDebrisPositions] = useState([]);

  const tcaPulseRef = useRef(0);

  // Fetch orbit trails when a conjunction is selected
  useEffect(() => {
    if (!selectedConjunction) {
      setPrimaryTrail(null);
      setSecondaryTrail(null);
      setTcaPositions(null);
      return;
    }

    const primaryNorad = selectedConjunction.primary?.norad_id;
    const secondaryNorad = selectedConjunction.secondary?.norad_id;
    if (!primaryNorad || !secondaryNorad) return;

    // Calculate minutes from now to TCA
    const tcaDate = new Date(selectedConjunction.tca);
    const now = new Date();
    const minutesToTca = (tcaDate - now) / 60000;

    // Fetch one full orbit for primary (steps=360 at 60s each ≈ 6 hours for LEO)
    const fetchTrails = async () => {
      try {
        const [priRes, secRes] = await Promise.all([
          propagateSatellite(primaryNorad, { steps: 360, step_seconds: 60 }),
          propagateSatellite(secondaryNorad, { steps: 360, step_seconds: 60 }),
        ]);

        const priPoints = (priRes.data.points || []).map((p) =>
          latLonAltToCartesian(p.latitude, p.longitude, p.altitude_km)
        );
        const secPoints = (secRes.data.points || []).map((p) =>
          latLonAltToCartesian(p.latitude, p.longitude, p.altitude_km)
        );

        setPrimaryTrail(priPoints);
        setSecondaryTrail(secPoints);

        // Get positions at TCA (or closest available point)
        // Use the midpoint of propagation as approximate current position
        if (priPoints.length > 0 && secPoints.length > 0) {
          setTcaPositions({
            primary: priPoints[0],
            secondary: secPoints[0],
            threatLevel: selectedConjunction.threat_level || 'LOW',
            missDistanceM: selectedConjunction.miss_distance_m,
          });
        }
      } catch (err) {
        console.error('Failed to fetch orbit trails:', err);
      }
    };

    fetchTrails();
  }, [selectedConjunction]);

  // Fetch debris-like positions for all conjunction secondaries
  useEffect(() => {
    if (conjunctions.length === 0) {
      setDebrisPositions([]);
      return;
    }

    const fetchDebris = async () => {
      try {
        // Get unique secondary NORAD IDs from conjunctions
        const noradIds = [...new Set(conjunctions.map((c) => c.secondary_norad_id).filter(Boolean))];
        if (noradIds.length === 0) return;

        // Propagate all secondaries in batch — use propagateSatellite for each
        // (propagateBatch only works for assets in DB, not catalog objects)
        const batchSize = 20;
        const positions = [];
        for (let i = 0; i < Math.min(noradIds.length, batchSize); i++) {
          try {
            const res = await propagateSatellite(noradIds[i], { steps: 1 });
            const pts = res.data.points || [];
            if (pts.length > 0) {
              const conj = conjunctions.find((c) => c.secondary_norad_id === noradIds[i]);
              positions.push({
                noradId: noradIds[i],
                name: conj?.secondary_name || `NORAD ${noradIds[i]}`,
                position: latLonAltToCartesian(pts[0].latitude, pts[0].longitude, pts[0].altitude_km),
                threatLevel: conj?.threat_level || 'LOW',
              });
            }
          } catch {
            // Skip objects we can't propagate
          }
        }
        setDebrisPositions(positions);
      } catch (err) {
        console.error('Failed to fetch debris positions:', err);
      }
    };

    fetchDebris();
  }, [conjunctions]);

  // Animate TCA pulse
  useFrame((_, delta) => {
    tcaPulseRef.current = (tcaPulseRef.current + delta * 2) % (Math.PI * 2);
  });

  const pulseScale = 1 + Math.sin(tcaPulseRef.current) * 0.3;

  // Build orbit trail geometry
  const primaryLineGeom = useMemo(() => {
    if (!primaryTrail || primaryTrail.length < 2) return null;
    const geom = new THREE.BufferGeometry();
    const positions = new Float32Array(primaryTrail.length * 3);
    for (let i = 0; i < primaryTrail.length; i++) {
      positions[i * 3] = primaryTrail[i][0];
      positions[i * 3 + 1] = primaryTrail[i][1];
      positions[i * 3 + 2] = primaryTrail[i][2];
    }
    geom.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    return geom;
  }, [primaryTrail]);

  const secondaryLineGeom = useMemo(() => {
    if (!secondaryTrail || secondaryTrail.length < 2) return null;
    const geom = new THREE.BufferGeometry();
    const positions = new Float32Array(secondaryTrail.length * 3);
    for (let i = 0; i < secondaryTrail.length; i++) {
      positions[i * 3] = secondaryTrail[i][0];
      positions[i * 3 + 1] = secondaryTrail[i][1];
      positions[i * 3 + 2] = secondaryTrail[i][2];
    }
    geom.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    return geom;
  }, [secondaryTrail]);

  // Miss distance line geometry (between primary and secondary at TCA)
  const missLineGeom = useMemo(() => {
    if (!tcaPositions) return null;
    const geom = new THREE.BufferGeometry();
    const positions = new Float32Array([
      ...tcaPositions.primary,
      ...tcaPositions.secondary,
    ]);
    geom.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    return geom;
  }, [tcaPositions]);

  const threatColor = tcaPositions
    ? THREAT_COLORS[tcaPositions.threatLevel] || THREAT_COLORS.LOW
    : THREAT_COLORS.LOW;

  return (
    <group>
      {/* Primary orbit trail */}
      {primaryLineGeom && (
        <line geometry={primaryLineGeom}>
          <lineBasicMaterial color="#448AFF" transparent opacity={0.6} linewidth={1} />
        </line>
      )}

      {/* Secondary orbit trail */}
      {secondaryLineGeom && (
        <line geometry={secondaryLineGeom}>
          <lineBasicMaterial color={threatColor} transparent opacity={0.5} linewidth={1} />
        </line>
      )}

      {/* Miss distance line at TCA */}
      {missLineGeom && (
        <line geometry={missLineGeom}>
          <lineDashedMaterial
            color="#ffffff"
            transparent
            opacity={0.8}
            dashSize={0.02}
            gapSize={0.01}
            linewidth={1}
          />
        </line>
      )}

      {/* TCA point markers */}
      {tcaPositions && (
        <>
          {/* Primary at TCA */}
          <mesh position={tcaPositions.primary}>
            <sphereGeometry args={[0.02, 16, 16]} />
            <meshBasicMaterial color="#448AFF" />
          </mesh>

          {/* Secondary at TCA — pulsing */}
          <mesh position={tcaPositions.secondary} scale={[pulseScale, pulseScale, pulseScale]}>
            <sphereGeometry args={[0.02, 16, 16]} />
            <meshBasicMaterial color={threatColor} />
          </mesh>

          {/* TCA glow ring around secondary */}
          <mesh position={tcaPositions.secondary} rotation={[Math.PI / 2, 0, 0]}>
            <torusGeometry args={[0.04 * pulseScale, 0.003, 8, 32]} />
            <meshBasicMaterial color={threatColor} transparent opacity={0.5} />
          </mesh>
        </>
      )}

      {/* Debris dots — secondary objects from all conjunctions */}
      {debrisPositions.map((debris) => (
        <mesh key={debris.noradId} position={debris.position}>
          <sphereGeometry args={[0.008, 6, 6]} />
          <meshBasicMaterial
            color={THREAT_COLORS[debris.threatLevel] || '#FF5252'}
          />
        </mesh>
      ))}
    </group>
  );
}
