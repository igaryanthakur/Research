import React, { useRef, useMemo, useEffect } from 'react';
import { useFrame } from '@react-three/fiber';
import { Torus, Cylinder, Sphere, RoundedBox, MeshDistortMaterial, Ring } from '@react-three/drei';
import * as THREE from 'three';

// ─── Types ────────────────────────────────────────────────────────────────────
interface ThreatOrbProps {
  riskScore: number;
}

// ─── Colour helper ────────────────────────────────────────────────────────────
const SAFE   = new THREE.Color('#00ffcc');
const DANGER = new THREE.Color('#ff2255');
const _tmp   = new THREE.Color();

// ─── Particles (memory-stable, instanced approach) ───────────────────────────
const Particles: React.FC<{ highRisk: boolean }> = ({ highRisk }) => {
  const ref = useRef<THREE.Points>(null);

  // Reduced to 200 particles — still visually rich, 60% cheaper
  const { positions, colors } = useMemo(() => {
    const COUNT = 200;
    const pos   = new Float32Array(COUNT * 3);
    const col   = new Float32Array(COUNT * 3);
    const base  = new THREE.Color('#00eeff');
    for (let i = 0; i < COUNT; i++) {
      const phi   = Math.acos(-1 + (2 * i) / COUNT);
      const theta = Math.sqrt(COUNT * Math.PI) * phi;
      const r     = 2.6 + Math.random() * 0.4;
      pos[i * 3]     = r * Math.cos(theta) * Math.sin(phi);
      pos[i * 3 + 1] = r * Math.sin(theta) * Math.sin(phi);
      pos[i * 3 + 2] = r * Math.cos(phi);
      col[i * 3]     = base.r;
      col[i * 3 + 1] = base.g;
      col[i * 3 + 2] = base.b;
    }
    return { positions: pos, colors: col };
  }, []);

  // Shared, memoised material — not recreated each render
  const material = useMemo(
    () =>
      new THREE.PointsMaterial({
        size: 0.03,
        vertexColors: true,
        transparent: true,
        opacity: 0.55,
        sizeAttenuation: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      }),
    []
  );

  // Dispose on unmount to prevent GPU leak
  useEffect(() => () => material.dispose(), [material]);

  useFrame(({ clock }) => {
    if (!ref.current) return;
    const t = clock.getElapsedTime();
    ref.current.rotation.y = t * 0.07;
    ref.current.rotation.z = t * 0.035;
    const s = 1 + Math.sin(t * 1.4) * 0.1;
    ref.current.scale.setScalar(s);
  });

  return (
    <points ref={ref}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
        <bufferAttribute attach="attributes-color"    args={[colors,    3]} />
      </bufferGeometry>
      <primitive object={material} attach="material" />
    </points>
  );
};

// ─── Main security object ─────────────────────────────────────────────────────
const SecurityObject: React.FC<ThreatOrbProps> = ({ riskScore }) => {
  const groupRef   = useRef<THREE.Group>(null);
  const lockRef    = useRef<THREE.Group>(null);
  const lockBodyRef = useRef<THREE.Mesh>(null);
  const ringRef    = useRef<THREE.Group>(null);
  const scannerRef = useRef<THREE.Group>(null);
  const beamRef    = useRef<THREE.Mesh>(null);

  // All materials memoised + disposed on unmount
  const lockMat = useMemo(
    () =>
      new THREE.MeshPhysicalMaterial({
        color: '#050505',
        metalness: 1,
        roughness: 0.1,
        clearcoat: 1,
        clearcoatRoughness: 0.1,
        emissive: '#00ff88',
        emissiveIntensity: 0.5,
      }),
    []
  );
  const rimMat = useMemo(
    () => new THREE.MeshStandardMaterial({ color: '#333', metalness: 1, roughness: 0.1 }),
    []
  );
  const beamMat = useMemo(
    () =>
      new THREE.MeshBasicMaterial({
        color: '#00eeff',
        transparent: true,
        opacity: 0.12,
        side: THREE.DoubleSide,
        depthWrite: false,
      }),
    []
  );
  const gridMat = useMemo(
    () =>
      new THREE.MeshBasicMaterial({
        color: '#00eeff',
        transparent: true,
        opacity: 0.08,
        wireframe: true,
        depthWrite: false,
      }),
    []
  );

  useEffect(
    () => () => {
      lockMat.dispose();
      rimMat.dispose();
      beamMat.dispose();
      gridMat.dispose();
    },
    [lockMat, rimMat, beamMat, gridMat]
  );

  // Replaced <Float> with manual sine math — eliminates internal rAF overhead
  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();

    // Breathing
    if (groupRef.current) {
      const breath = 1 + Math.sin(t * 1.4) * 0.035;
      groupRef.current.scale.setScalar(breath);
    }

    // Lock idle float + colour shift
    if (lockRef.current) {
      lockRef.current.rotation.y  = t * 0.22;
      lockRef.current.position.y  = Math.sin(t * 1.1) * 0.12;
    }
    if (lockBodyRef.current) {
      const mix = (Math.sin(t * 1.4) + 1) / 2;
      const mat = lockBodyRef.current.material as THREE.MeshPhysicalMaterial;
      _tmp.copy(SAFE).lerp(DANGER, riskScore > 60 ? mix : mix * 0.2);
      mat.emissive.copy(_tmp);
      mat.emissiveIntensity = 0.35 + mix * 0.55;
    }

    // Holographic ring
    if (ringRef.current) {
      ringRef.current.rotation.z = -t * 0.38;
    }

    // Scanner orbit — manual math, no Float component
    if (scannerRef.current) {
      const speed  = 1.4;
      const radius = 1.15;
      scannerRef.current.position.x = Math.sin(t * speed) * radius;
      scannerRef.current.position.y = Math.cos(t * speed * 0.65) * 0.38 + 0.75;
      scannerRef.current.position.z = Math.cos(t * speed) * radius * 0.5 + 1.1;
      scannerRef.current.lookAt(0, 0, 0);
    }

    // Beam pulse
    if (beamRef.current) {
      const mat = beamRef.current.material as THREE.MeshBasicMaterial;
      mat.opacity = 0.04 + Math.abs(Math.sin(t * 4.5)) * 0.13;
    }
  });

  const highRisk = riskScore >= 70;

  return (
    <group ref={groupRef} position={[0, 1.4, 0]}>
      {/* Holographic floor rings */}
      <group rotation={[-Math.PI / 2, 0, 0]} position={[0, -1, 0]}>
        <Ring args={[1.48, 1.5, 64]}>
          <meshBasicMaterial color="#00eeff" transparent opacity={0.25} />
        </Ring>
        <Ring args={[1.76, 1.77, 64]}>
          <meshBasicMaterial color="#00eeff" transparent opacity={0.09} />
        </Ring>
        <group ref={ringRef}>
          <Ring args={[0.48, 1.38, 32, 1]}>
            <primitive object={gridMat} attach="material" />
          </Ring>
        </group>
      </group>

      {/* Security lock */}
      <group ref={lockRef}>
        {/* Shackle */}
        <group position={[0, 0.44, 0]}>
          <Torus args={[0.54, 0.075, 16, 48, Math.PI]}>
            <meshStandardMaterial color="#222" metalness={1} roughness={0.1} />
          </Torus>
          <Torus args={[0.54, 0.01, 8, 48, Math.PI]} position={[0, 0, 0.05]}>
            <meshBasicMaterial color="#00eeff" transparent opacity={0.45} />
          </Torus>
        </group>

        {/* Lock body */}
        <RoundedBox
          ref={lockBodyRef}
          args={[1.08, 0.92, 0.42]}
          radius={0.11}
          smoothness={6}
          position={[0, -0.1, 0]}
        >
          <primitive object={lockMat} attach="material" />
        </RoundedBox>

        {/* Status orb */}
        <Sphere args={[0.13, 24, 24]} position={[0, -0.1, 0.22]}>
          <MeshDistortMaterial color={highRisk ? '#ff2255' : '#00eeff'} speed={2} distort={0.28} />
        </Sphere>
      </group>

      {/* Scanner (manual orbit, no Float) */}
      <group ref={scannerRef}>
        <Torus args={[0.43, 0.038, 16, 64]}>
          <primitive object={rimMat} attach="material" />
        </Torus>
        <Cylinder args={[0.41, 0.41, 0.045, 28]} rotation={[Math.PI / 2, 0, 0]}>
          <MeshDistortMaterial
            color="#00eeff"
            speed={1.2}
            distort={0.16}
            transparent
            opacity={0.45}
            metalness={0.2}
            roughness={0}
          />
        </Cylinder>
        <Cylinder args={[0.035, 0.055, 0.55, 12]} position={[0, -0.65, 0]}>
          <meshStandardMaterial color="#050505" metalness={1} roughness={0.2} />
        </Cylinder>
        <Sphere args={[0.07, 12, 12]} position={[0, -0.94, 0]}>
          <meshBasicMaterial color="#00eeff" />
        </Sphere>
        {/* Volumetric beam */}
        <mesh ref={beamRef} position={[0, 0, -0.55]} rotation={[Math.PI / 2, 0, 0]}>
          <coneGeometry args={[0.41, 1.6, 28, 1, true]} />
          <primitive object={beamMat} attach="material" />
        </mesh>
      </group>

      {/* Particles */}
      <Particles highRisk={highRisk} />

      {/* Scene lights */}
      <pointLight position={[4,  4,  4]} intensity={0.45} color="#00eeff" />
      <pointLight position={[-4, -4, -4]} intensity={0.35} color="#ff2255" />
    </group>
  );
};

export default SecurityObject;