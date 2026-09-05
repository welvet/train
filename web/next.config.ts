import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  transpilePackages: ["@fluentui-emoji/react"],
};

export default nextConfig;
