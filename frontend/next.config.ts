import type { NextConfig } from "next";

const API_URL = process.env.NEXUS_API_URL ?? "http://127.0.0.1:8010";

const nextConfig: NextConfig = {
  // Every screen renders per-user data fetched on the client, so component caching brings no benefit here.
  cacheComponents: false,
  // Compression would buffer Server-Sent Events proxied from the API.
  compress: false,
  output: "standalone",
  experimental: {
    // Local-model calls (analysis, long generations) can legitimately exceed the 30s default.
    proxyTimeout: 600_000,
    // Uploads are validated by the API (25 MB limit); the proxy must not cut them off first.
    proxyClientMaxBodySize: "30mb",
  },
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
