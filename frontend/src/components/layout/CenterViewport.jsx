import { useRef } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, Stars } from '@react-three/drei';
import EarthGlobe from '../three/EarthGlobe';
import SatelliteMarkers from '../three/SatelliteMarkers';
import ConjunctionLines from '../three/ConjunctionLines';
import CameraController from '../three/CameraController';
import './CenterViewport.css';

function Scene() {
  const controlsRef = useRef();

  return (
    <>
      <ambientLight intensity={0.15} />
      <directionalLight position={[5, 3, 5]} intensity={1.2} color="#ffffff" />
      <Stars radius={50} depth={50} count={3000} factor={3} saturation={0} fade speed={0.5} />
      <EarthGlobe />
      <SatelliteMarkers />
      <ConjunctionLines />
      <CameraController controlsRef={controlsRef} />
      <OrbitControls
        ref={controlsRef}
        enablePan={true}
        enableZoom={true}
        enableRotate={true}
        minDistance={1.5}
        maxDistance={20}
        rotateSpeed={0.5}
        zoomSpeed={0.8}
      />
    </>
  );
}

export default function CenterViewport() {
  return (
    <div className="center-viewport">
      <Canvas
        camera={{ position: [0, 0, 4], fov: 45 }}
        gl={{ antialias: true, alpha: false }}
        style={{ background: '#060A13' }}
      >
        <Scene />
      </Canvas>
    </div>
  );
}
