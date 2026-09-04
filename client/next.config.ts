import type { NextConfig } from "next";

const nextConfig: NextConfig = {};

// The production Docker image runs Next.js' minimal standalone server. Vercel
// packages Next.js with its own adapter and should use the default build output.
if (!process.env.VERCEL) {
    nextConfig.output = "standalone";
}

export default nextConfig;
