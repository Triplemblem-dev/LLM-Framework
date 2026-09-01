/** @type {import('next').NextConfig} */
const nextConfig = {
  // Produces a self-contained .next/standalone build (only the node_modules
  // files actually needed at runtime) so the Docker image doesn't have to
  // ship the full node_modules tree - see frontend/Dockerfile.
  output: "standalone",
};

export default nextConfig;
