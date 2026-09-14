import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "export",
  distDir: process.env.NODE_ENV === "development" ? ".next-dev" : "out",
};

export default nextConfig;
