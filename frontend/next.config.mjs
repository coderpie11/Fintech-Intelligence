/**
 * Backend origin for the optional `/bff` proxy. Rewrites are baked in at
 * build time, so production sets NEXT_PUBLIC_API_URL. Local development keeps
 * hitting the FastAPI server on port 8000 exactly as before.
 */
const API_BASE = (
  process.env.API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://localhost:8000"
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
