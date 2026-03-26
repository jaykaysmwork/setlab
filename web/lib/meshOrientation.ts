/**
 * Extra Euler (degrees) for mod_building GLBs after spec rotation_deg (no in-app global UI; per-module Δ in SpecPanel).
 * Reads build-time NEXT_PUBLIC_* (root .env via next.config loadEnvConfig).
 */
export function parseMeshExtraDegFromEnv(): [number, number, number] {
  const p = (key: string): number => {
    const v = process.env[key];
    if (v === undefined || v === "") return 0;
    const n = parseFloat(v);
    return Number.isFinite(n) ? n : 0;
  };
  return [
    p("NEXT_PUBLIC_HD_MESH_EXTRA_RX_DEG"),
    p("NEXT_PUBLIC_HD_MESH_EXTRA_RY_DEG"),
    p("NEXT_PUBLIC_HD_MESH_EXTRA_RZ_DEG"),
  ];
}
