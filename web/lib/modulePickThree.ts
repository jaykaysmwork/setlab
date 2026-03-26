import * as THREE from "three";

/** Non-selected: multiply albedo — works with textured GLBs (color is often white). */
const DIM_ALBEDO_MULT = 0.5;
const DIM_EMISSIVE_MULT = 0.28;

/** Selected: subtle cool rim so pick is obvious without flattening normals. */
const SEL_EMISSIVE_ADD = new THREE.Color(0x143848);
const SEL_EMISSIVE_INT_MIN = 0.22;
const SEL_COLOR_TINT = new THREE.Color(0x6ec0d8);
const SEL_BASIC_COLOR_LERP = 0.2;

/** Walk named nodes in spec; tag each Mesh with userData.selectableModuleId. */
export function tagMeshesWithModuleId(
  root: THREE.Object3D,
  moduleIds: Set<string>,
): void {
  root.traverse((child) => {
    if (!(child instanceof THREE.Mesh) || !child.geometry) return;
    let o: THREE.Object3D | null = child;
    while (o) {
      if (o.name && moduleIds.has(o.name)) {
        child.userData.selectableModuleId = o.name;
        break;
      }
      o = o.parent;
    }
  });
}

function ensurePickOrig(mat: THREE.Material): void {
  if (mat.userData._setlabPickStored) return;
  mat.userData._setlabPickStored = true;
  const m = mat as THREE.MeshStandardMaterial;
  if ("color" in m && m.color?.isColor) {
    mat.userData._setlabPickColor = m.color.clone();
  }
  if ("emissive" in m && m.emissive?.isColor) {
    mat.userData._setlabPickEmissive = m.emissive.clone();
    mat.userData._setlabPickEmissiveIntensity = m.emissiveIntensity ?? 0;
  }
}

function restoreMaterial(mat: THREE.Material): void {
  const m = mat as THREE.MeshStandardMaterial;
  const oc = mat.userData._setlabPickColor as THREE.Color | undefined;
  const oe = mat.userData._setlabPickEmissive as THREE.Color | undefined;
  if (oc && "color" in m) m.color.copy(oc);
  if (oe && "emissive" in m) {
    m.emissive.copy(oe);
    m.emissiveIntensity = mat.userData._setlabPickEmissiveIntensity ?? 0;
  }
}

/** Others while something is selected: darker / flatter (visible on texture-heavy mats). */
function dimMaterial(mat: THREE.Material): void {
  const m = mat as THREE.MeshStandardMaterial;
  const oc = mat.userData._setlabPickColor as THREE.Color | undefined;
  if (oc && "color" in m) {
    m.color.copy(oc).multiplyScalar(DIM_ALBEDO_MULT);
  }
  const oe = mat.userData._setlabPickEmissive as THREE.Color | undefined;
  if (oe && "emissive" in m) {
    m.emissive.copy(oe).multiplyScalar(DIM_EMISSIVE_MULT);
    m.emissiveIntensity =
      (mat.userData._setlabPickEmissiveIntensity ?? 0) * DIM_EMISSIVE_MULT;
  }
}

/** The focused module: restore base + light accent. */
function styleSelectedMaterial(mat: THREE.Material): void {
  restoreMaterial(mat);
  const m = mat as THREE.MeshStandardMaterial;
  if ("emissive" in m && m.emissive) {
    const oe = mat.userData._setlabPickEmissive as THREE.Color | undefined;
    if (oe) m.emissive.copy(oe).add(SEL_EMISSIVE_ADD);
    else m.emissive.copy(SEL_EMISSIVE_ADD);
    const bi = mat.userData._setlabPickEmissiveIntensity ?? 0;
    m.emissiveIntensity = Math.max(bi, SEL_EMISSIVE_INT_MIN);
  } else if ("color" in m && m.color) {
    const oc = mat.userData._setlabPickColor as THREE.Color | undefined;
    if (oc) m.color.copy(oc).lerp(SEL_COLOR_TINT, SEL_BASIC_COLOR_LERP);
    else m.color.lerp(SEL_COLOR_TINT, SEL_BASIC_COLOR_LERP);
  }
}

export type SelectionPickStyleOptions = {
  /** All meshes under `root` count as this module (GLB subtree). */
  fixedModuleId?: string;
};

/**
 * When `selectedModuleId` is set: that module gets a subtle highlight; others are
 * darkened (albedo mult — works with Tripo-style textured materials).
 * When null, everything restored.
 */
export function applySelectionPickStyle(
  root: THREE.Object3D,
  selectedModuleId: string | null,
  options?: SelectionPickStyleOptions,
): void {
  root.traverse((child) => {
    if (!(child instanceof THREE.Mesh)) return;
    const mid =
      options?.fixedModuleId ??
      (child.userData.selectableModuleId as string | undefined);
    if (!mid) return;

    const mats = Array.isArray(child.material)
      ? child.material
      : [child.material];
    for (const mat of mats) {
      if (!mat || typeof mat !== "object") continue;
      ensurePickOrig(mat);
      if (selectedModuleId === null) {
        restoreMaterial(mat);
      } else if (mid === selectedModuleId) {
        styleSelectedMaterial(mat);
      } else {
        dimMaterial(mat);
      }
    }
  });
}
