"use client";

import { Canvas, invalidate, useThree } from "@react-three/fiber";
import { OrbitControls, Grid, useGLTF } from "@react-three/drei";
import { Suspense, useCallback, useEffect, useLayoutEffect, useMemo } from "react";
import * as THREE from "three";
import type { SetSpec } from "@/lib/api";
import { ImportedMeshModule } from "@/components/ImportedMeshModule";
import { ViewportModulePick } from "@/components/ViewportModulePick";
import {
  applySelectionPickStyle,
  tagMeshesWithModuleId,
} from "@/lib/modulePickThree";
import {
  buildGlbExtraEulerChain,
  glbRotationSuspenseKey,
} from "@/lib/meshGlbRotation";
import { buildSceneEnvironment } from "@/lib/specEnvironment";
import SpecSceneEnvironment from "@/components/SpecSceneEnvironment";

function Model({
  url,
  meshGlbs,
  moduleIds,
  meshedOnly,
  selectedModuleId,
}: {
  url: string;
  meshGlbs: Record<string, string>;
  moduleIds: Set<string>;
  meshedOnly: boolean;
  selectedModuleId: string | null;
}) {
  const { scene } = useGLTF(url);
  const { camera, controls } = useThree();

  const meshGlbIds = useMemo(() => new Set(Object.keys(meshGlbs)), [meshGlbs]);

  // Clone only when scene or moduleIds changes — NOT when meshGlbIds changes.
  // Visibility is updated imperatively below to avoid scene.clone() on every poll tick.
  const cloned = useMemo(() => {
    const c = scene.clone();
    if (moduleIds.size > 0) tagMeshesWithModuleId(c, moduleIds);
    return c;
  }, [scene, moduleIds]);

  // Imperatively update visibility without replacing the object. useLayoutEffect
  // applies it before paint so meshed modules never flash their proxy box for a
  // frame on (re)mount when meshGlbs is already populated.
  useLayoutEffect(() => {
    if (moduleIds.size === 0) return;
    cloned.traverse((child) => {
      if (!child.name || !moduleIds.has(child.name)) return;
      child.visible = meshGlbIds.has(child.name) ? false : !meshedOnly;
    });
    invalidate();
  }, [cloned, meshGlbIds, moduleIds, meshedOnly]);

  useEffect(() => {
    applySelectionPickStyle(cloned, selectedModuleId);
    invalidate();
  }, [cloned, selectedModuleId]);

  useEffect(() => {
    const box = new THREE.Box3().setFromObject(scene);
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z);
    const distance = maxDim * 1.8;

    camera.position.set(
      center.x + distance * 0.6,
      center.y + distance * 0.5,
      center.z + distance * 0.6,
    );
    camera.lookAt(center);
    camera.updateProjectionMatrix();

    if (controls && "target" in controls) {
      (controls as any).target.copy(center);
      (controls as any).update();
    }
    // frameloop is "demand": imperative camera/controls mutations don't auto-render,
    // so kick one frame after the fit.
    invalidate();

    return () => {
      useGLTF.clear(url);
    };
  }, [url, scene, camera, controls]);

  return <primitive object={cloned} />;
}

function Fallback() {
  return (
    <mesh>
      <boxGeometry args={[1, 1, 1]} />
      <meshStandardMaterial color="#444" wireframe />
    </mesh>
  );
}

interface Props {
  gltfUrl: string | null;
  spec?: SetSpec | null;
  meshGlbs?: Record<string, string>;
  meshedOnly?: boolean;
  /** Degrees: extra RX, RY, RZ after spec — mod_building GLB only (roads stay fixed). */
  meshGlbExtraDeg?: [number, number, number];
  /** Per-module extra Euler (°), applied after spec (and after building global if mod_building). */
  perModuleGlbExtraDeg?: Record<string, [number, number, number]>;
  selectedModuleId?: string | null;
  onViewportSelectModuleId?: (id: string | null) => void;
}

export default function Viewer3D({
  gltfUrl,
  spec,
  meshGlbs = {},
  meshedOnly = false,
  meshGlbExtraDeg = [0, 0, 0],
  perModuleGlbExtraDeg = {},
  selectedModuleId = null,
  onViewportSelectModuleId,
}: Props) {
  const hasLoadedGlbs = Object.keys(meshGlbs).length > 0;
  const effectiveMeshedOnly = meshedOnly && hasLoadedGlbs;

  const moduleIds = useMemo(
    () => new Set(spec?.modules.map((m) => m.id) ?? []),
    [spec],
  );

  const sceneVisual = useMemo(
    () => buildSceneEnvironment(spec?.environment),
    [spec],
  );

  // frameloop is "demand": some environment changes mutate three objects
  // imperatively (e.g. FogExpBridge sets scene.fog) and don't auto-invalidate,
  // so kick a frame whenever the resolved scene visual changes.
  useEffect(() => {
    invalidate();
  }, [sceneVisual]);

  const meshModules = useMemo(() => {
    if (!spec) return [];
    return Object.entries(meshGlbs)
      .map(([moduleId, glbUrl]) => {
        const mod = spec.modules.find((m) => m.id === moduleId);
        if (!mod) return null;
        return {
          moduleId,
          glbUrl,
          asset: mod.asset,
          position: mod.position,
          rotationDeg: mod.rotation_deg,
          scale: mod.scale,
        };
      })
      .filter(Boolean) as {
      moduleId: string;
      glbUrl: string;
      asset: string;
      position: [number, number, number];
      rotationDeg: [number, number, number];
      scale: [number, number, number];
    }[];
  }, [spec, meshGlbs]);

  const pickCb = useCallback(
    (id: string | null) => {
      onViewportSelectModuleId?.(id);
    },
    [onViewportSelectModuleId],
  );

  return (
    <div className="w-full h-full bg-[#111119] rounded-xl overflow-hidden relative">
      <div className="pointer-events-none absolute bottom-2 left-2 z-10 text-[10px] text-[#666] bg-[#111119]/85 backdrop-blur px-2 py-1 rounded">
        클릭/리스트 선택 · 하늘·해·안개는 스펙 environment 반영 · 선택 모듈 청록 와이어
      </div>
      <Canvas
        camera={{ position: [30, 25, 30], fov: 50 }}
        gl={{ antialias: true }}
        frameloop="demand"
      >
        <Suspense fallback={<Fallback />}>
          <SpecSceneEnvironment visual={sceneVisual} />
          {gltfUrl ? (
            <Model
              url={gltfUrl}
              meshGlbs={meshGlbs}
              moduleIds={moduleIds}
              meshedOnly={effectiveMeshedOnly}
              selectedModuleId={selectedModuleId}
            />
          ) : (
            <Fallback />
          )}
        </Suspense>
        {meshModules.map(
          ({ moduleId, glbUrl, asset, position, rotationDeg, scale }) => {
            const chain = buildGlbExtraEulerChain(
              asset,
              meshGlbExtraDeg,
              perModuleGlbExtraDeg,
              moduleId,
            );
            return (
              <Suspense
                key={glbRotationSuspenseKey(moduleId, rotationDeg, chain)}
                fallback={null}
              >
                <ImportedMeshModule
                  url={glbUrl}
                  moduleId={moduleId}
                  selectedModuleId={selectedModuleId}
                  position={position}
                  rotationDeg={rotationDeg}
                  scale={scale}
                  extraEulerChainDeg={chain}
                />
              </Suspense>
            );
          },
        )}

        <Grid
          infiniteGrid
          cellSize={1}
          sectionSize={5}
          cellColor="#1a1a2e"
          sectionColor="#2a2a3e"
          fadeDistance={80}
        />
        <OrbitControls makeDefault />
        {onViewportSelectModuleId ? (
          <ViewportModulePick onSelectModuleId={pickCb} />
        ) : null}
      </Canvas>
    </div>
  );
}
