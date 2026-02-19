import { useRef, useMemo, useState } from 'react';
import { useFrame, useLoader } from '@react-three/fiber';
import { Sphere } from '@react-three/drei';
import * as THREE from 'three';

const EARTH_TEXTURE_URL = 'https://unpkg.com/three-globe@2.31.1/example/img/earth-blue-marble.jpg';

export default function EarthGlobe() {
  const meshRef = useRef();
  const [textureLoaded, setTextureLoaded] = useState(false);

  // Try loading the Earth texture
  const texture = useMemo(() => {
    const loader = new THREE.TextureLoader();
    const tex = loader.load(
      EARTH_TEXTURE_URL,
      () => setTextureLoaded(true),
      undefined,
      () => setTextureLoaded(false),
    );
    tex.colorSpace = THREE.SRGBColorSpace;
    return tex;
  }, []);

  // Textured material when loaded, fallback to procedural look
  const material = useMemo(() => {
    if (textureLoaded) {
      return new THREE.MeshPhongMaterial({
        map: texture,
        bumpScale: 0.02,
        specular: new THREE.Color('#111111'),
        shininess: 5,
      });
    }
    return new THREE.MeshPhongMaterial({
      color: new THREE.Color('#1a4a7a'),
      emissive: new THREE.Color('#0a1a3a'),
      emissiveIntensity: 0.1,
      shininess: 25,
      specular: new THREE.Color('#336699'),
    });
  }, [textureLoaded, texture]);

  // Slow rotation
  useFrame((_, delta) => {
    if (meshRef.current) {
      meshRef.current.rotation.y += delta * 0.02;
    }
  });

  return (
    <group>
      {/* Earth sphere */}
      <Sphere ref={meshRef} args={[1, 64, 64]} material={material} />

      {/* Atmosphere glow — outer shell */}
      <Sphere args={[1.015, 64, 64]}>
        <meshPhongMaterial
          color="#4488ff"
          transparent
          opacity={0.08}
          side={THREE.BackSide}
        />
      </Sphere>

      {/* Atmosphere haze — larger shell for glow effect */}
      <Sphere args={[1.06, 32, 32]}>
        <meshBasicMaterial
          color="#1a66cc"
          transparent
          opacity={0.03}
          side={THREE.BackSide}
        />
      </Sphere>

      {/* Equator ring */}
      <mesh rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[1.01, 0.001, 8, 128]} />
        <meshBasicMaterial color="#334466" transparent opacity={0.3} />
      </mesh>
    </group>
  );
}
