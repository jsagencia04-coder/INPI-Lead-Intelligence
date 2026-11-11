import type { NextConfig } from "next";

// As telas chamam /api/... no próprio endereço, e o Next.js repassa para o backend.
// Assim funciona igual no computador, no GitHub Codespaces e em produção, sem CORS.
const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  experimental: {
    // O RM<N>.zip da RPI tem ~10 MB; o padrão do repasse é 10 MB e 30 s.
    middlewareClientMaxBodySize: "200mb",
    proxyTimeout: 180_000,
  },
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` },
      { source: "/health", destination: `${BACKEND_URL}/health` },
      { source: "/webhooks/:path*", destination: `${BACKEND_URL}/webhooks/:path*` },
      { source: "/ws/:path*", destination: `${BACKEND_URL}/ws/:path*` },
    ];
  },
};

export default nextConfig;
