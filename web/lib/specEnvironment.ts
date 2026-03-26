/**
 * Map set_spec.json `environment` → Three.js / drei Sky + lights + fog.
 * Aligns with setlab.models.EnvironmentSettings (time_of_day, weather, fog_density, sun_intensity, sun_color_temp).
 */

import { calcPosFromAngles } from "@react-three/drei";
import { Vector3 } from "three";
import type { EnvironmentSettings } from "@/lib/api";

const DEFAULT_ENV: Required<EnvironmentSettings> = {
  time_of_day: "noon",
  weather: "clear",
  fog_density: 0.02,
  sun_intensity: 10,
  sun_color_temp: 6500,
};

type SkyPreset = {
  inclination: number;
  azimuth: number;
  rayleigh: number;
  turbidity: number;
  mieCoefficient: number;
  mieDirectionalG: number;
};

function normalizeTimeKey(raw: string): string {
  return raw.toLowerCase().trim().replace(/\s+/g, "_");
}

/** drei's Sky: inclination/azimuth → sunPosition via same formula as <Sky />. */
function skyPresetForTime(timeRaw: string): SkyPreset {
  const key = normalizeTimeKey(timeRaw);
  const map: Record<string, SkyPreset> = {
    dawn: {
      inclination: 0.52,
      azimuth: 0.12,
      rayleigh: 1.4,
      turbidity: 7,
      mieCoefficient: 0.004,
      mieDirectionalG: 0.86,
    },
    morning: {
      inclination: 0.58,
      azimuth: 0.2,
      rayleigh: 0.55,
      turbidity: 5,
      mieCoefficient: 0.005,
      mieDirectionalG: 0.82,
    },
    noon: {
      inclination: 0.65,
      azimuth: 0.25,
      rayleigh: 0.45,
      turbidity: 4,
      mieCoefficient: 0.005,
      mieDirectionalG: 0.8,
    },
    afternoon: {
      inclination: 0.6,
      azimuth: 0.32,
      rayleigh: 0.55,
      turbidity: 5,
      mieCoefficient: 0.005,
      mieDirectionalG: 0.8,
    },
    golden_hour: {
      inclination: 0.505,
      azimuth: 0.38,
      rayleigh: 2.4,
      turbidity: 5,
      mieCoefficient: 0.004,
      mieDirectionalG: 0.88,
    },
    sunset: {
      inclination: 0.492,
      azimuth: 0.44,
      rayleigh: 3.2,
      turbidity: 6,
      mieCoefficient: 0.0035,
      mieDirectionalG: 0.9,
    },
    dusk: {
      inclination: 0.475,
      azimuth: 0.5,
      rayleigh: 3.8,
      turbidity: 8,
      mieCoefficient: 0.003,
      mieDirectionalG: 0.92,
    },
    night: {
      inclination: 0.22,
      azimuth: 0.58,
      rayleigh: 0.08,
      turbidity: 2,
      mieCoefficient: 0.002,
      mieDirectionalG: 0.75,
    },
  };
  return map[key] ?? map.noon;
}

function clamp(n: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, n));
}

/** Approximate sRGB 0–1 from correlated color temperature (K). */
export function kelvinToRgb(kelvin: number): [number, number, number] {
  const k = clamp(kelvin, 1000, 40000) / 100;
  let r: number;
  let g: number;
  let b: number;
  if (k <= 66) {
    r = 255;
    g = clamp(99.4708025861 * Math.log(k) - 161.1195681661, 0, 255);
  } else {
    r = clamp(329.698727446 * Math.pow(k - 60, -0.1332047592), 0, 255);
    g = clamp(288.1221695283 * Math.pow(k - 60, -0.0755148492), 0, 255);
  }
  if (k >= 66) {
    b = 255;
  } else if (k <= 19) {
    b = 0;
  } else {
    b = clamp(138.5177312231 * Math.log(k - 10) - 305.0447927307, 0, 255);
  }
  return [r / 255, g / 255, b / 255];
}

function weatherMultipliers(weatherRaw: string): {
  sunScale: number;
  ambientScale: number;
  turbidityScale: number;
  rayleighScale: number;
  iblIntensity: number;
} {
  const w = weatherRaw.toLowerCase().trim();
  if (w.includes("storm") || w.includes("rain"))
    return { sunScale: 0.45, ambientScale: 0.35, turbidityScale: 1.35, rayleighScale: 0.75, iblIntensity: 0.35 };
  if (w.includes("snow"))
    return { sunScale: 0.85, ambientScale: 0.55, turbidityScale: 1.2, rayleighScale: 1.1, iblIntensity: 0.55 };
  if (w.includes("fog"))
    return { sunScale: 0.55, ambientScale: 0.45, turbidityScale: 1.5, rayleighScale: 0.65, iblIntensity: 0.4 };
  if (w.includes("overcast") || w.includes("cloud"))
    return { sunScale: 0.65, ambientScale: 0.5, turbidityScale: 1.45, rayleighScale: 0.7, iblIntensity: 0.45 };
  return { sunScale: 1, ambientScale: 1, turbidityScale: 1, rayleighScale: 1, iblIntensity: 0.55 };
}

export type SceneEnvironmentVisual = {
  useSky: boolean;
  skyDistance: number;
  sky: SkyPreset;
  /** Main directional: color + intensity + position (world). */
  sun: { position: [number, number, number]; intensity: number; color: string };
  fill: { position: [number, number, number]; intensity: number; color: string };
  ambientIntensity: number;
  ambientColor: string;
  /** CSS hex for canvas clear when not using full sky fill — still set for fog blend */
  backgroundHex: string;
  fog: { color: string; density: number } | null;
  environmentPreset: "city" | "sunset" | "dawn" | "night" | "studio";
  environmentIntensity: number;
};

function hexFromRgb(rgb: [number, number, number]): string {
  const [r, g, b] = rgb.map((x) => Math.round(clamp(x, 0, 1) * 255));
  return `#${[r, g, b].map((n) => n.toString(16).padStart(2, "0")).join("")}`;
}

export function buildSceneEnvironment(
  env: EnvironmentSettings | null | undefined,
): SceneEnvironmentVisual {
  const merged: Required<EnvironmentSettings> = {
    ...DEFAULT_ENV,
    ...env,
    time_of_day: env?.time_of_day?.trim() || DEFAULT_ENV.time_of_day,
    weather: env?.weather?.trim() || DEFAULT_ENV.weather,
    fog_density:
      typeof env?.fog_density === "number" && !Number.isNaN(env.fog_density)
        ? env.fog_density
        : DEFAULT_ENV.fog_density,
    sun_intensity:
      typeof env?.sun_intensity === "number" && !Number.isNaN(env.sun_intensity)
        ? env.sun_intensity
        : DEFAULT_ENV.sun_intensity,
    sun_color_temp:
      typeof env?.sun_color_temp === "number" && !Number.isNaN(env.sun_color_temp)
        ? Math.round(env.sun_color_temp)
        : DEFAULT_ENV.sun_color_temp,
  };

  const wx = weatherMultipliers(merged.weather);
  const skyBase = skyPresetForTime(merged.time_of_day);
  const sky: SkyPreset = {
    ...skyBase,
    turbidity: clamp(skyBase.turbidity * wx.turbidityScale, 1, 20),
    rayleigh: clamp(skyBase.rayleigh * wx.rayleighScale, 0.02, 6),
  };

  const sunVec = calcPosFromAngles(sky.inclination, sky.azimuth, new Vector3());
  const sunDist = 280;
  const sunPos: [number, number, number] = [
    sunVec.x * sunDist,
    sunVec.y * sunDist,
    sunVec.z * sunDist,
  ];

  const rgb = kelvinToRgb(merged.sun_color_temp);
  const sunColor = hexFromRgb(rgb);
  const ambientTint = kelvinToRgb(
    clamp(merged.sun_color_temp * 0.92, 2000, 12000),
  );
  const ambientColor = hexFromRgb(ambientTint);

  // Spec uses ~0–100 for sun_intensity; map to Three directional (roughly physical-ish preview).
  const sunIntensity =
    clamp(merged.sun_intensity / 10, 0.05, 4.5) * wx.sunScale;
  const ambientIntensity = clamp(0.22 + sunIntensity * 0.12, 0.08, 0.85) * wx.ambientScale;

  const fillIntensity = clamp(sunIntensity * 0.22, 0.05, 0.55);
  const fillPos: [number, number, number] = [
    -sunPos[0] * 0.35 + sunPos[2] * 0.2,
    sunPos[1] * 0.4 + 40,
    -sunPos[2] * 0.35 - sunPos[0] * 0.15,
  ];

  const fogDensity = clamp(merged.fog_density, 0, 1);
  const fogColorRgb = kelvinToRgb(clamp(merged.sun_color_temp * 0.85, 2500, 9000));
  const fogColor = hexFromRgb(fogColorRgb);
  const fog =
    fogDensity > 0.001
      ? { color: fogColor, density: clamp(fogDensity * 0.045, 0.002, 0.18) }
      : null;

  const bgRgb = kelvinToRgb(clamp(merged.sun_color_temp * 0.55, 2000, 8000));
  const backgroundHex = hexFromRgb([
    bgRgb[0] * 0.15,
    bgRgb[1] * 0.16,
    bgRgb[2] * 0.22,
  ]);

  const tkey = normalizeTimeKey(merged.time_of_day);
  let environmentPreset: SceneEnvironmentVisual["environmentPreset"] = "city";
  if (tkey.includes("night")) environmentPreset = "night";
  else if (tkey.includes("sunset") || tkey.includes("dusk") || tkey === "golden_hour")
    environmentPreset = "sunset";
  else if (tkey.includes("dawn")) environmentPreset = "dawn";

  const isNight = tkey === "night" || merged.sun_intensity < 0.35;

  return {
    useSky: true,
    skyDistance: 450000,
    sky,
    sun: { position: sunPos, intensity: sunIntensity, color: sunColor },
    fill: {
      position: fillPos,
      intensity: fillIntensity,
      color: isNight ? "#8899bb" : "#cfe8ff",
    },
    ambientIntensity,
    ambientColor,
    backgroundHex,
    fog,
    environmentPreset,
    environmentIntensity: wx.iblIntensity,
  };
}
