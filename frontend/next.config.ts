import type { NextConfig } from "next";
// `output: "standalone"` est requis pour l'image Docker (frontend/Dockerfile),
// mais casse le routage sur Vercel (404 NOT_FOUND). Vercel définit VERCEL=1
// pendant le build : on désactive donc standalone uniquement dans ce cas.
const nextConfig: NextConfig = {
  ...(process.env.VERCEL ? {} : { output: "standalone" }),
  async headers() {
    return [{
      source: "/(.*)",
      headers: [
        { key: "X-Content-Type-Options", value: "nosniff" },
        { key: "X-Frame-Options", value: "DENY" },
        { key: "Referrer-Policy", value: "same-origin" },
        { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
      ],
    }];
  },
};
export default nextConfig;
