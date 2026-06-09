"use client";

import { useLayoutEffect, useEffect, useMemo, useRef, useState } from "react";
import { invalidate } from "@react-three/fiber";
import { useGLTF } from "@react-three/drei";
import * as THREE from "three";
import { applySelectionPickStyle } from "@/lib/modulePickThree";

const DEG2RAD = Math.PI / 180;

function quatFromDegXYZ(rx: number, ry: number, rz: number): THREE.Quaternion {
  return new THREE.Quaternion().setFromEuler(
    new THREE.Euler(rx * DEG2RAD, ry * DEG2RAD, rz * DEG2RAD, "XYZ"),
  );
}

/** Bake every Mesh under `source` into one group: hierarchy rotations become vertex positions. */
function bakeToFlatGroup(source: THREE.Object3D): THREE.Group {
  const g = new THREE.Group();
  source.updateMatrixWorld(true);
  source.traverse((child) => {
    if (!(child instanceof THREE.Mesh) || !child.geometry) return;
    const geom = child.geometry.clone();
    geom.applyMatrix4(child.matrixWorld);
    const mat = child.material;
    const mats = Array.isArray(mat) ? mat.map((m) => m.clone()) : mat.clone();
    g.add(new THREE.Mesh(geom, mats));
  });
  return g;
}

function disposeSubtree(obj: THREE.Object3D) {
  obj.traverse((o) => {
    if (o instanceof THREE.Mesh && o.geometry) o.geometry.dispose();
  });
}

/**
 * spec rotation_deg, then each extra tri as XYZ Euler (°) in order: q = q_spec * q_0 * q_1 * …
 */
export function ImportedMeshModule({
  url,
  moduleId,
  position,
  rotationDeg,
  extraEulerChainDeg,
  scale = [1, 1, 1] as [number, number, number],
  positionOffset = [0, 0, 0] as [number, number, number],
  selectedModuleId = null,
}: {
  url: string;
  moduleId: string;
  selectedModuleId?: string | null;
  position: [number, number, number];
  rotationDeg: [number, number, number];
  extraEulerChainDeg: [number, number, number][];
  scale?: [number, number, number];
  positionOffset?: [number, number, number];
}) {
  const { scene } = useGLTF(url);
  const outerRef = useRef<THREE.Group>(null);
  const innerRef = useRef<THREE.Group>(null);
  const selectedRef = useRef(selectedModuleId);
  selectedRef.current = selectedModuleId;

  const [pickBounds, setPickBounds] = useState<{
    center: [number, number, number];
    size: [number, number, number];
  } | null>(null);

  const chainKey = JSON.stringify(extraEulerChainDeg);

  const worldQuat = useMemo(() => {
    let q = quatFromDegXYZ(rotationDeg[0], rotationDeg[1], rotationDeg[2]);
    for (const [rx, ry, rz] of extraEulerChainDeg) {
      q.multiply(quatFromDegXYZ(rx, ry, rz));
    }
    return q;
  }, [rotationDeg[0], rotationDeg[1], rotationDeg[2], chainKey]);

  useLayoutEffect(() => {
    outerRef.current?.quaternion.copy(worldQuat);
  }, [worldQuat]);

  useEffect(() => {
    if (!innerRef.current) return;
    const flat = bakeToFlatGroup(scene.clone(true));

    const box = new THREE.Box3().setFromObject(flat);
    if (box.isEmpty()) {
      innerRef.current.clear();
      setPickBounds(null);
      return;
    }

    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());

    const sx = size.x > 0 ? 1 / size.x : 1;
    const sy = size.y > 0 ? 1 / size.y : 1;
    const sz = size.z > 0 ? 1 / size.z : 1;

    flat.scale.set(sx, sy, sz);
    flat.position.set(-center.x * sx, -center.y * sy, -center.z * sz);

    flat.updateMatrixWorld(true);
    const bb = new THREE.Box3().setFromObject(flat);
    const bc = new THREE.Vector3();
    const bs = new THREE.Vector3();
    bb.getCenter(bc);
    bb.getSize(bs);
    setPickBounds({ center: [bc.x, bc.y, bc.z], size: [bs.x, bs.y, bs.z] });

    const g = innerRef.current;
    while (g.children.length) {
      const ch = g.children[0];
      g.remove(ch);
      disposeSubtree(ch);
    }
    g.add(flat);
    flat.traverse((child) => {
      if (child instanceof THREE.Mesh) {
        child.userData.selectableModuleId = moduleId;
      }
    });

    applySelectionPickStyle(g, selectedRef.current, { fixedModuleId: moduleId });
    invalidate();

    return () => {
      useGLTF.clear(url);
      if (!innerRef.current) return;
      while (innerRef.current.children.length) {
        const ch = innerRef.current.children[0];
        innerRef.current.remove(ch);
        disposeSubtree(ch);
      }
    };
  }, [url, scene, moduleId]);

  useEffect(() => {
    const g = innerRef.current;
    if (!g || g.children.length === 0) return;
    applySelectionPickStyle(g, selectedModuleId, {
      fixedModuleId: moduleId,
    });
    invalidate();
  }, [selectedModuleId, moduleId]);

  const outline =
    selectedModuleId !== null &&
    selectedModuleId === moduleId &&
    pickBounds !== null
      ? pickBounds
      : null;

  return (
    <group
      ref={outerRef}
      position={[
        position[0] + positionOffset[0],
        position[1] + positionOffset[1],
        position[2] + positionOffset[2],
      ]}
      scale={scale}
    >
      <group>
        <group ref={innerRef} />
        {outline ? (
          <mesh position={outline.center}>
            <boxGeometry
              args={[
                Math.max(outline.size[0], 0.02) * 1.08,
                Math.max(outline.size[1], 0.02) * 1.08,
                Math.max(outline.size[2], 0.02) * 1.08,
              ]}
            />
            <meshBasicMaterial
              color="#2dd4bf"
              wireframe
              transparent
              opacity={0.95}
              depthTest
              depthWrite={false}
            />
          </mesh>
        ) : null}
      </group>
    </group>
  );
}
