import { resolve } from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  turbopack: { root: resolve(process.cwd(), "..") },
  output: "export",
  distDir: process.env.NODE_ENV === "development" ? ".next-dev" : "out",
};

export default nextConfig;
