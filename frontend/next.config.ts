import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // The API is a separate read-only Python service. Pages fetch it server-side,
  // so no browser CORS negotiation is involved; this rewrite exists only for the
  // few client-side calls (search suggestions) that need a same-origin path.
  async rewrites() {
    const target = process.env.API_BASE_URL ?? "http://127.0.0.1:8080/api/v1";
    return [{ source: "/api/v1/:path*", destination: `${target}/:path*` }];
  },
};

export default nextConfig;
