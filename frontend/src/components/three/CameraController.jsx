import { useRef, useEffect } from 'react';
import { useThree, useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import useAssetStore from '../../stores/assetStore';
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

/**
 * Compute camera offset distance based on satellite altitude.
 * LEO (~400km, r≈1.06): offset 0.8  →  camera at ~1.86
 * MEO (~20000km, r≈4.1): offset 2.5  →  camera at ~6.6
 * GEO (~35786km, r≈6.6): offset 4.0  →  camera at ~10.6
 */
function getCameraOffset(satDistance) {
  if (satDistance < 1.5) return 0.8;   // LEO
  if (satDistance < 3.5) return 1.8;   // MEO-low
  if (satDistance < 5.0) return 2.5;   // MEO
  return 4.0;                          // GEO+
}

export default function CameraController({ controlsRef }) {
  const { camera } = useThree();
  const selectedAssetId = useAssetStore((s) => s.selectedAssetId);
  const assets = useAssetStore((s) => s.assets);
  const selectedConjunction = useConjunctionStore((s) => s.selectedConjunction);

  const flyTarget = useRef(null);
  const flyLookAt = useRef(null);
  const flyProgress = useRef(1); // 1 = not flying
  const startPos = useRef(new THREE.Vector3());
  const startTarget = useRef(new THREE.Vector3());

  /** Start a fly-to animation to the given satellite position. */
  const startFlyTo = (satPos) => {
    const direction = satPos.clone().normalize();
    const offset = getCameraOffset(satPos.length());
    const cameraOffset = direction.clone().multiplyScalar(offset);
    const targetPos = satPos.clone().add(cameraOffset);

    startPos.current.copy(camera.position);
    startTarget.current.set(0, 0, 0);
    if (controlsRef?.current) {
      startTarget.current.copy(controlsRef.current.target);
    }

    flyTarget.current = targetPos;
    flyLookAt.current = satPos;
    flyProgress.current = 0;
  };

  // When an asset is selected, fly camera to it
  useEffect(() => {
    if (!selectedAssetId) return;

    const asset = assets.find((a) => a.id === selectedAssetId);
    if (!asset) return;

    const flyToAsset = async () => {
      try {
        const res = await propagateSatellite(asset.norad_id, { steps: 1 });
        const pts = res.data.points || [];
        if (pts.length === 0) return;

        const satPos = latLonAltToCartesian(pts[0].latitude, pts[0].longitude, pts[0].altitude_km);
        startFlyTo(satPos);
      } catch (err) {
        console.error('Fly-to asset failed:', err);
      }
    };

    flyToAsset();
  }, [selectedAssetId]);

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
        startFlyTo(satPos);
      } catch (err) {
        console.error('Fly-to conjunction failed:', err);
      }
    };

    flyToConjunction();
  }, [selectedConjunction]);

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
