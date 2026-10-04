import type { NextConfig } from "next";

const nextConfig: NextConfig = {
    async rewrites() {
        const backendUrl = process.env.BACKEND_URL || "http://localhost:3050";
        return [
            {
                source: "/api/v1/:path*",
                destination: `${backendUrl}/api/v1/:path*`,
            },
        ];
    },
    allowedDevOrigins: ["ai-legal.day-la-hiep.site"],
};

export default nextConfig;
