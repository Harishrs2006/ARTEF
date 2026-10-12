/** @type {import('next').NextConfig} */
const apiProxyTarget = (process.env.API_PROXY_TARGET || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1").replace(/\/+$/, "");
const normalizedApiProxyTarget = apiProxyTarget.endsWith("/api/v1") ? apiProxyTarget : `${apiProxyTarget}/api/v1`;

const nextConfig = {
  reactStrictMode: false,
  // Standalone server for the Docker image only: on Windows it needs symlink privileges.
  output: process.env.NEXT_OUTPUT_STANDALONE === "true" ? "standalone" : undefined,
  eslint: {
    // Lint runs as its own CI step (`pnpm lint`) instead of inside `next build`.
    ignoreDuringBuilds: true,
  },
  typescript: {
    ignoreBuildErrors: false,
  },
  experimental: {
    optimizePackageImports: ["lucide-react", "@radix-ui/react-icons"],
  },
  images: {
    remotePatterns: [{ protocol: "http", hostname: "localhost" }],
  },
  // Production optimizations
  productionBrowserSourceMaps: false,
  onDemandEntries: {
    maxInactiveAge: 25 * 1000,
    pagesBufferLength: 2,
  },
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${normalizedApiProxyTarget}/:path*`,
      },
    ];
  },
};

export default nextConfig;
