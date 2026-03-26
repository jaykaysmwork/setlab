import path from "node:path";
import { fileURLToPath } from "node:url";
import { loadEnvConfig } from "@next/env";
import type { NextConfig } from "next";

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.join(here, "..");
loadEnvConfig(repoRoot);

const nextConfig: NextConfig = {};

export default nextConfig;
