"use client";

import { useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";

/** Squared px — drag farther than this counts as orbit, not pick */
const DRAG_THRESHOLD_PX2 = 100;

/**
 * Raycast pick on the WebGL canvas (orbit-friendly: ignores drags).
 * Meshes must set userData.selectableModuleId = module id.
 */
export function ViewportModulePick({
  onSelectModuleId,
}: {
  onSelectModuleId: (id: string | null) => void;
}) {
  const { camera, gl, scene } = useThree();
  const raycaster = useMemo(() => new THREE.Raycaster(), []);
  const pointer = useMemo(() => new THREE.Vector2(), []);
  const downRef = useRef<{ x: number; y: number } | null>(null);

  useEffect(() => {
    const el = gl.domElement;
    const onDown = (e: PointerEvent) => {
      if (e.button !== 0) return;
      downRef.current = { x: e.clientX, y: e.clientY };
    };
    const onUp = (e: PointerEvent) => {
      if (e.button !== 0 || !downRef.current) return;
      const d = downRef.current;
      downRef.current = null;
      const dx = e.clientX - d.x;
      const dy = e.clientY - d.y;
      if (dx * dx + dy * dy > DRAG_THRESHOLD_PX2) return;

      const rect = el.getBoundingClientRect();
      pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointer, camera);
      const hits = raycaster.intersectObjects(scene.children, true);
      for (const h of hits) {
        let o: THREE.Object3D | null = h.object;
        while (o) {
          if (o.userData?.selectableModuleId) {
            onSelectModuleId(o.userData.selectableModuleId as string);
            return;
          }
          o = o.parent;
        }
      }
      onSelectModuleId(null);
    };
    el.addEventListener("pointerdown", onDown);
    el.addEventListener("pointerup", onUp);
    return () => {
      el.removeEventListener("pointerdown", onDown);
      el.removeEventListener("pointerup", onUp);
    };
  }, [camera, gl, scene, raycaster, pointer, onSelectModuleId]);

  return null;
}
