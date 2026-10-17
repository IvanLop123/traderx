import { fileURLToPath } from "node:url";
import path from "node:path";
const config = {
  distDir: process.env.TRADERX_NEXT_DIST || ".next",
  outputFileTracingRoot: path.dirname(fileURLToPath(import.meta.url)),
  poweredByHeader: false,
  devIndicators: false,
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination:
          (process.env.BACKEND_URL || "http://127.0.0.1:8000") +
          "/api/v1/:path*",
      },
    ];
  },
};
export default config;
