"use client";

import { useEffect } from "react";
import { useThree } from "@react-three/fiber";
import { Sky, Environment } from "@react-three/drei";
import * as THREE from "three";
import type { SceneEnvironmentVisual } from "@/lib/specEnvironment";

function FogExpBridge({ color, density }: { color: string; density: number }) {
  const { scene } = useThree();
  useEffect(() => {
    const prev = scene.fog;
    scene.fog = new THREE.FogExp2(color, density);
    return () => {
      scene.fog = prev;
    };
  }, [scene, color, density]);
  return null;
}

/** Sky + spec-driven sun/fill/ambient + optional fog + low-intensity IBL for PBR. */
export default function SpecSceneEnvironment({
  visual,
}: {
  visual: SceneEnvironmentVisual;
}) {
  return (
    <>
      <color attach="background" args={[visual.backgroundHex]} />
      {visual.useSky ? (
        <Sky
          distance={visual.skyDistance}
          inclination={visual.sky.inclination}
          azimuth={visual.sky.azimuth}
          rayleigh={visual.sky.rayleigh}
          turbidity={visual.sky.turbidity}
          mieCoefficient={visual.sky.mieCoefficient}
          mieDirectionalG={visual.sky.mieDirectionalG}
        />
      ) : null}
      <ambientLight intensity={visual.ambientIntensity} color={visual.ambientColor} />
      <directionalLight
        castShadow={false}
        position={visual.sun.position}
        intensity={visual.sun.intensity}
        color={visual.sun.color}
      />
      <directionalLight
        position={visual.fill.position}
        intensity={visual.fill.intensity}
        color={visual.fill.color}
      />
      {visual.fog ? (
        <FogExpBridge color={visual.fog.color} density={visual.fog.density} />
      ) : null}
      <Environment
        preset={visual.environmentPreset}
        environmentIntensity={visual.environmentIntensity}
      />
    </>
  );
}
