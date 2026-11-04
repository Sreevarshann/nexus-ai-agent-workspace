import type { NextConfig } from "next";

const API_URL = process.env.NEXUS_API_URL ?? "http://127.0.0.1:8010";

const nextConfig: NextConfig = {
  // Every screen renders per-user data fetched on the client, so component caching brings no benefit here.
  cacheComponents: false,
  // Compression would buffer Server-Sent Events proxied from the API.
  compress: false,
  output: "standalone",
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${API_URL}/api/:path*` },
      { source: "/mcp/:path*", destination: `${API_URL}/mcp/:path*` },
    ];
  },
};

export default nextConfig;
