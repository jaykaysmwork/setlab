import path from "node:path";
import { fileURLToPath } from "node:url";
import { loadEnvConfig } from "@next/env";
import type { NextConfig } from "next";

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.join(here, "..");
loadEnvConfig(repoRoot);

const isStaticExport = process.env.SETLAB_STATIC_EXPORT === "1";
const basePath = (process.env.NEXT_PUBLIC_BASE_PATH || "").trim();

const backendUrl = (
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000"
).replace(/\/$/, "");

const nextConfig: NextConfig = {
  experimental: {
    // Claude generate can take 60-120s; default proxy timeout is 30s
    proxyTimeout: 180_000,
  },
  ...(basePath ? { basePath } : {}),
  ...(isStaticExport
    ? {
        output: "export" as const,
        images: { unoptimized: true },
      }
    : {
        // Dev / server mode: proxy /api/* to FastAPI so the browser
        // never needs to know the backend port.
        async rewrites() {
          return [
            {
              source: "/api/:path*",
              destination: `${backendUrl}/api/:path*`,
            },
          ];
        },
      }),
};

export default nextConfig;
