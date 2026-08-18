import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./i18n/request.ts");

// Same-origin API: the browser calls /api/* and Next proxies to the FastAPI backend.
// In prod the reverse proxy co-locates them, so client code always uses relative /api.
const backend = process.env.BACKEND_URL || "http://localhost:8000";

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Production validation builds must never share artifacts with `next dev`.
  // The live development server uses `.next`; `npm run build` uses `.next-build`.
  distDir: process.env.NEXT_DIST_DIR || (process.env.NODE_ENV === "development" ? ".next" : ".next-build"),
  // Disable Next's gzip: it compresses the proxied /api SSE stream in dev, which
  // BUFFERS it (whole response arrives at once after a delay instead of streaming).
  // In prod, Caddy handles compression and scopes it away from /api.
  compress: false,
  // Lean production image (server.js + minimal deps) for the prod Dockerfile.
  output: "standalone",
  // Hide the dev-mode overlay badge (the "N" indicator).
  devIndicators: false,
  async redirects() {
    return [
      { source: "/app/chat", destination: "/", permanent: true },
      { source: "/app/chat/:id", destination: "/c/:id", permanent: true },
      { source: "/app/developer", destination: "/console", permanent: true },
      { source: "/privacy", destination: "https://coreai.uz/privacy/", permanent: true },
      { source: "/terms", destination: "https://coreai.uz/terms/", permanent: true },
    ];
  },
  // Dev only: proxy /api to the backend. In prod, Caddy routes /api directly to the
  // backend (this rewrite is never hit).
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default withNextIntl(nextConfig);
