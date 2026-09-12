import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Keep development artifacts separate from production builds. Sharing `.next`
  // can leave Webpack pointing at a chunk that was removed by the other process.
  distDir: process.env.NODE_ENV === "development" ? ".next-dev" : ".next",
};

export default nextConfig;
