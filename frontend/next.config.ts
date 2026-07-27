import type { NextConfig } from "next";
import fs from "fs";
import path from "path";

// Lee la versión de release.conf en build time — nunca queda desincronizada
// como pasaba con el badge hardcodeado del README.
function readPlatformVersion(): string {
  try {
    const raw = fs.readFileSync(path.join(__dirname, "..", "release.conf"), "utf-8");
    const match = raw.match(/^PLATFORM_VERSION="?([^"\n]+)"?/m);
    return match?.[1] ?? "0.0";
  } catch {
    return "0.0";
  }
}

const nextConfig: NextConfig = {
  output: "standalone",
  env: {
    NEXT_PUBLIC_VOXIKAM_VERSION: readPlatformVersion(),
  },
};

export default nextConfig;
