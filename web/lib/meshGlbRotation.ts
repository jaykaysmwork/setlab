/** Extra Euler steps after spec: q = q_spec * ∏ q_i. Building-only global, then optional per-module. */
export function buildGlbExtraEulerChain(
  asset: string,
  buildingExtraDeg: [number, number, number],
  perModuleDelta: Record<string, [number, number, number]>,
  moduleId: string,
): [number, number, number][] {
  const chain: [number, number, number][] = [];
  if (asset === "mod_building") {
    const [rx, ry, rz] = buildingExtraDeg;
    if (rx !== 0 || ry !== 0 || rz !== 0) {
      chain.push([rx, ry, rz]);
    }
  }
  const d = perModuleDelta[moduleId];
  if (d) {
    const [rx, ry, rz] = d;
    if (rx !== 0 || ry !== 0 || rz !== 0) {
      chain.push([rx, ry, rz]);
    }
  }
  return chain;
}

export function glbRotationSuspenseKey(
  moduleId: string,
  rotationDeg: [number, number, number],
  chain: [number, number, number][],
): string {
  return `${moduleId}-${rotationDeg.join(",")}-${JSON.stringify(chain)}`;
}
