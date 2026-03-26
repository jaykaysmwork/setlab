"use client";

import { Canvas, invalidate, useThree, useFrame } from "@react-three/fiber";
import { OrbitControls, useGLTF } from "@react-three/drei";
import { Suspense, useCallback, useEffect, useMemo, useRef } from "react";
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

function Scene({
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

  const cloned = useMemo(() => {
    const c = scene.clone();
    if (moduleIds.size === 0) return c;
    c.traverse((child) => {
      if (!child.name || !moduleIds.has(child.name)) return;
      const hasGlb = !!meshGlbs[child.name];
      if (hasGlb) {
        child.visible = false;
      } else {
        child.visible = !meshedOnly;
      }
    });
    tagMeshesWithModuleId(c, moduleIds);
    return c;
  }, [scene, meshGlbs, moduleIds, meshedOnly]);

  useEffect(() => {
    applySelectionPickStyle(cloned, selectedModuleId);
    invalidate();
  }, [cloned, selectedModuleId]);

  useEffect(() => {
    const box = new THREE.Box3().setFromObject(scene);
    const center = box.getCenter(new THREE.Vector3());
    cloned.position.set(-center.x, 0, -center.z);

    camera.position.set(0, 1.7, 0);
    camera.updateProjectionMatrix();

    if (controls && "target" in controls) {
      const ctrl = controls as any;
      ctrl.target.set(0, 1.7, 0);
      ctrl.update();
    }

    return () => {
      useGLTF.clear(url);
    };
  }, [url, scene, cloned, camera, controls]);

  return <primitive object={cloned} />;
}

const WALK_SPEED = 5;
const RUN_SPEED = 12;

function WASDMovement() {
  const { camera, controls } = useThree();
  const keys = useRef<Record<string, boolean>>({});

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement
      )
        return;
      keys.current[e.key.toLowerCase()] = true;
    };
    const onKeyUp = (e: KeyboardEvent) => {
      keys.current[e.key.toLowerCase()] = false;
    };
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
    };
  }, []);

  useFrame((_, delta) => {
    const k = keys.current;

    const forward = new THREE.Vector3();
    camera.getWorldDirection(forward);
    forward.y = 0;
    forward.normalize();

    const right = new THREE.Vector3();
    right.crossVectors(forward, camera.up).normalize();

    const move = new THREE.Vector3();
    if (k.w || k.arrowup) move.add(forward);
    if (k.s || k.arrowdown) move.sub(forward);
    if (k.d || k.arrowright) move.add(right);
    if (k.a || k.arrowleft) move.sub(right);

    if (move.lengthSq() > 0) {
      const speed = k.shift ? RUN_SPEED : WALK_SPEED;
      move.normalize().multiplyScalar(speed * delta);
      camera.position.add(move);
      if (controls && "target" in controls) {
        (controls as any).target.add(move);
        (controls as any).update();
      }
    }
  });

  return null;
}

interface Props {
  gltfUrl: string | null;
  spec?: SetSpec | null;
  meshGlbs?: Record<string, string>;
  meshedOnly?: boolean;
  meshGlbExtraDeg?: [number, number, number];
  perModuleGlbExtraDeg?: Record<string, [number, number, number]>;
  selectedModuleId?: string | null;
  onViewportSelectModuleId?: (id: string | null) => void;
}

export default function VRViewer({
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

  const { meshModules, sceneOffset } = useMemo(() => {
    if (!spec || !gltfUrl) return { meshModules: [], sceneOffset: [0, 0, 0] as [number, number, number] };

    const allPositions = spec.modules.map((m) => m.position);
    const cx =
      allPositions.reduce((s, p) => s + p[0], 0) / (allPositions.length || 1);
    const cz =
      allPositions.reduce((s, p) => s + p[2], 0) / (allPositions.length || 1);
    const offset: [number, number, number] = [-cx, 0, -cz];

    const modules = Object.entries(meshGlbs)
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

    return { meshModules: modules, sceneOffset: offset };
  }, [spec, meshGlbs, gltfUrl]);

  const pickCb = useCallback(
    (id: string | null) => {
      onViewportSelectModuleId?.(id);
    },
    [onViewportSelectModuleId],
  );

  return (
    <div className="w-full h-full bg-[#0a0a14] rounded-xl overflow-hidden relative">
      <div className="absolute bottom-3 left-3 z-10 text-[11px] text-[#555] bg-[#0a0a14]/80 backdrop-blur px-2 py-1 rounded space-y-0.5">
        <div>Drag to look &middot; WASD to move &middot; Shift to run</div>
        {onViewportSelectModuleId ? (
          <div className="text-[10px] text-[#666]">
            클릭으로 모듈 선택 · 빈 곳 → 해제
          </div>
        ) : null}
      </div>

      <Canvas
        camera={{ position: [0, 1.7, 0], fov: 75, near: 0.01 }}
        gl={{ antialias: true }}
        frameloop="always"
      >
        <Suspense fallback={null}>
          <SpecSceneEnvironment visual={sceneVisual} />
          {gltfUrl ? (
            <Scene
              url={gltfUrl}
              meshGlbs={meshGlbs}
              moduleIds={moduleIds}
              meshedOnly={effectiveMeshedOnly}
              selectedModuleId={selectedModuleId}
            />
          ) : null}
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
                  positionOffset={sceneOffset}
                />
              </Suspense>
            );
          },
        )}

        <WASDMovement />
        <OrbitControls
          makeDefault
          enablePan={false}
          enableZoom={false}
          minDistance={0.01}
          maxDistance={0.01}
          rotateSpeed={0.5}
        />
        {onViewportSelectModuleId ? (
          <ViewportModulePick onSelectModuleId={pickCb} />
        ) : null}
      </Canvas>
    </div>
  );
}
