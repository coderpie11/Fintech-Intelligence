/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/bff/:path*",
        destination: "http://127.0.0.1:8001/:path*",
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
