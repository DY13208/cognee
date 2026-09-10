import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emit .next/standalone: a self-contained server bundle with only the
  // node_modules the app actually reaches. This is what the Docker runtime
  // stage copies, and it is why the published image ships no dev dependencies.
  output: "standalone",
  // Self-hosted docker maps the UI to a LAN IP (e.g. 192.168.0.204:3030).
  // Next 16 blocks cross-origin access to /_next/* in dev unless listed here —
  // without it the shell can render while pages spin forever.
  allowedDevOrigins: [
    "localhost",
    "127.0.0.1",
    "192.168.0.204",
    "192.168.1.114",
  ],
  images: {
    remotePatterns: [{
      protocol: "https",
      hostname: "lh3.googleusercontent.com",
    }],
  },
};

export default nextConfig;
