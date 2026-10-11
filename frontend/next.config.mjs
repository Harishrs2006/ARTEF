/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: false,
  // Standalone server for the Docker image only: on Windows it needs symlink privileges.
  output: process.env.NEXT_OUTPUT_STANDALONE === "true" ? "standalone" : undefined,
  experimental: {
    optimizePackageImports: ["lucide-react", "@radix-ui/react-icons"],
  },
  images: {
    domains: ["localhost"],
  },
  // Production optimizations
  productionBrowserSourceMaps: false,
  onDemandEntries: {
    maxInactiveAge: 25 * 1000,
    pagesBufferLength: 2,
  },
  async rewrites() {
    // BACKEND_URL lets Docker point at the api service; local dev defaults to :8000.
    const backend = process.env.BACKEND_URL || "http://localhost:8000";
    return [
      {
        source: "/api/v1/:path*",
        destination: `${backend}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
