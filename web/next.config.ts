import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Output as standalone for Docker/Cloud Run deployment
  output: "standalone",
};

export default nextConfig;
