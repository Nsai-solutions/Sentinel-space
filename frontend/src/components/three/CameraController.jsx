import { useRef, useEffect } from 'react';
import { useThree, useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import useConjunctionStore from '../../stores/conjunctionStore';
import { propagateSatellite } from '../../api/client';

const EARTH_RADIUS_KM = 6378.137;

function latLonAltToCartesian(lat, lon, alt) {
  const phi = (90 - lat) * (Math.PI / 180);
  const theta = (lon + 180) * (Math.PI / 180);
  const r = (EARTH_RADIUS_KM + alt) / EARTH_RADIUS_KM;
  return new THREE.Vector3(
    -(r * Math.sin(phi) * Math.cos(theta)),
    r * Math.cos(phi),
    r * Math.sin(phi) * Math.sin(theta),
  );
}

export default function CameraController({ controlsRef }) {
  const { camera } = useThree();
  const selectedConjunction = useConjunctionStore((s) => s.selectedConjunction);

  const flyTarget = useRef(null);
  const flyLookAt = useRef(null);
  const flyProgress = useRef(1); // 1 = not flying
  const startPos = useRef(new THREE.Vector3());
  const startTarget = useRef(new THREE.Vector3());

  // When a conjunction is selected, fetch position and start fly-to
  useEffect(() => {
    if (!selectedConjunction) return;

    const primaryNorad = selectedConjunction.primary?.norad_id;
    if (!primaryNorad) return;

    const flyToConjunction = async () => {
      try {
        const res = await propagateSatellite(primaryNorad, { steps: 1 });
        const pts = res.data.points || [];
        if (pts.length === 0) return;

        const satPos = latLonAltToCartesian(pts[0].latitude, pts[0].longitude, pts[0].altitude_km);

        // Camera should look at the satellite from a reasonable distance
        const direction = satPos.clone().normalize();
        const cameraOffset = direction.clone().multiplyScalar(0.8);
        const targetPos = satPos.clone().add(cameraOffset);

        // Store animation state
        startPos.current.copy(camera.position);
        startTarget.current.set(0, 0, 0); // current orbit controls target
        if (controlsRef?.current) {
          startTarget.current.copy(controlsRef.current.target);
        }

        flyTarget.current = targetPos;
        flyLookAt.current = satPos;
        flyProgress.current = 0;
      } catch (err) {
        console.error('Fly-to failed:', err);
      }
    };

    flyToConjunction();
  }, [selectedConjunction, camera, controlsRef]);

  // Animate camera
  useFrame((_, delta) => {
    if (flyProgress.current >= 1 || !flyTarget.current || !flyLookAt.current) return;

    flyProgress.current = Math.min(1, flyProgress.current + delta * 1.5);
    const t = smoothstep(flyProgress.current);

    // Interpolate camera position
    camera.position.lerpVectors(startPos.current, flyTarget.current, t);

    // Interpolate orbit controls target
    if (controlsRef?.current) {
      controlsRef.current.target.lerpVectors(startTarget.current, flyLookAt.current, t);
      controlsRef.current.update();
    }
  });

  return null;
}

function smoothstep(t) {
  return t * t * (3 - 2 * t);
}
