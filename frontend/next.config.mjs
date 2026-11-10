/**
 * Backend origin for the `/bff` proxy.
 *
 * Rewrites are baked into the routes manifest at build time, so set the
 * variable when building for production (Cloudflare Pages):
 *   NEXT_PUBLIC_API_URL=https://fintech-intelligence-backend.onrender.com
 * Falls back to the local FastAPI port so `npm run dev` is unchanged.
 */
const API_BASE = (
  process.env.API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://127.0.0.1:8001"
).replace(/\/+$/, "");

/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/bff/:path*",
        destination: `${API_BASE}/:path*`,
      },
    ];
  },
  // Old URLs kept alive as real HTTP redirects. Redirect-only server
  // components are avoided because a statically rendered `redirect()` ships
  // an empty 307 with no Location header.
  async redirects() {
    return [
      { source: "/academy", destination: "/learn", permanent: false },
      { source: "/academy/:track", destination: "/learn/:track", permanent: false },
      { source: "/ai-quant", destination: "/ai-quant-hub", permanent: false },
    ];
  },
};

export default nextConfig;
