import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const nextConfig: NextConfig = {
  // Emit .next/standalone: a self-contained server bundle with only the
  // node_modules the app actually reaches. This is what the Docker runtime
  // stage copies, and it is why the published image ships no dev dependencies.
  output: "standalone",
  // Browser opens http://127.0.0.1:3000 while the container advertises localhost.
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  turbopack: {},
  images: {
    remotePatterns: [{
      protocol: "https",
      hostname: "lh3.googleusercontent.com",
    }],
  },
};

export default withNextIntl(nextConfig);
