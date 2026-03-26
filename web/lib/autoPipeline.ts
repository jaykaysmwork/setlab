/**
 * New Scene → Generate 후 자동 실행 범위.
 * NEXT_PUBLIC_AUTO_PIPELINE_AFTER_GENERATE:
 *   (unset) | true | 1 | mesh+hd | all → Rodin 전 모듈(GLB) → 끝나면 HD(건물)
 *   hd | images+hd | hd-only → 일반 메시 건너뛰고, 곧바로 HD(이미지→GLB)
 *   mesh → 메시 만
 *   false | 0 | off → 자동 없음
 *
 * HD만 쓸 때: 건물은 이미지+Rodin HD로 GLB가 생기고, 도로/인도 등은 HD 대상이
 * 아니면 박스로 남습니다. 그때는 Generate 3D로 보충하세요.
 */

function truthyEnv(v: string | undefined): boolean {
  if (!v) return false;
  const s = v.toLowerCase().trim();
  return s === "1" || s === "true" || s === "yes" || s === "on";
}

export function parseAutoPipelineAfterGenerate(): {
  mesh: boolean;
  hd: boolean;
} {
  const raw =
    process.env.NEXT_PUBLIC_AUTO_PIPELINE_AFTER_GENERATE?.toLowerCase().trim() ??
    "";
  if (raw === "false" || raw === "0" || raw === "off") {
    return { mesh: false, hd: false };
  }
  if (raw === "mesh") {
    return { mesh: true, hd: false };
  }
  if (
    raw === "hd" ||
    raw === "images+hd" ||
    raw === "hd-only" ||
    raw === "hd_only"
  ) {
    return { mesh: false, hd: true };
  }
  return { mesh: true, hd: true };
}

/**
 * 메시/HD 자동 단계가 끝난 뒤 Rodin 머티리얼 향상 → UE Deploy 까지 이을지.
 *
 * NEXT_PUBLIC_AUTO_STUDIO_COMPLETE:
 *   1 | true | yes → material + deploy (Marble 제외, 비용 절약)
 *   full | all | complete → material + deploy + Marble(원경) 자동
 * NEXT_PUBLIC_AUTO_MATERIAL_AFTER_PIPELINE=1 → rodin_texture_only 자동 시작
 * NEXT_PUBLIC_AUTO_DEPLOY_AFTER_PIPELINE=1 → 위가 끝난 뒤(또는 머티리얼 생략 시) Deploy
 * NEXT_PUBLIC_AUTO_MARBLE_AFTER_GENERATE=1 → Generate 직후 World Labs Marble (full 없이 단독)
 * NEXT_PUBLIC_AUTO_MATERIAL_STYLE=generic_weathered (등) — 머티리얼 프리셋
 */
export function parseAutoPostPipeline(): {
  material: boolean;
  deploy: boolean;
  marble: boolean;
  materialStyle: string;
} {
  const scRaw =
    process.env.NEXT_PUBLIC_AUTO_STUDIO_COMPLETE?.toLowerCase().trim() ?? "";
  const studioLite =
    scRaw === "1" ||
    scRaw === "true" ||
    scRaw === "yes" ||
    scRaw === "on";
  const studioFull =
    scRaw === "full" ||
    scRaw === "all" ||
    scRaw === "complete" ||
    scRaw === "everything";
  const material =
    studioLite ||
    studioFull ||
    truthyEnv(process.env.NEXT_PUBLIC_AUTO_MATERIAL_AFTER_PIPELINE);
  const deploy =
    studioLite ||
    studioFull ||
    truthyEnv(process.env.NEXT_PUBLIC_AUTO_DEPLOY_AFTER_PIPELINE);
  const marble =
    studioFull ||
    truthyEnv(process.env.NEXT_PUBLIC_AUTO_MARBLE_AFTER_GENERATE);
  const materialStyle =
    process.env.NEXT_PUBLIC_AUTO_MATERIAL_STYLE?.trim() ||
    "generic_weathered";
  return { material, deploy, marble, materialStyle };
}
