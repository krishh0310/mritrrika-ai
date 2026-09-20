import path from "node:path";

import type { NextConfig } from "next";

const config: NextConfig = {
  reactStrictMode: true,
  // This app is one workspace of a monorepo; without this Next guesses the
  // tracing root and warns about it on every build.
  outputFileTracingRoot: path.join(import.meta.dirname, "../.."),
  // The FastAPI base URL is the one thing the browser bundle needs to know.
  // Everything else it learns by calling that API (§5 -- no business logic
  // duplicated in a frontend).
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
  },
  // Both workspace packages ship TypeScript source rather than a build step,
  // so Next has to compile them alongside the app.
  transpilePackages: ["@mrittika/shared-types", "@mrittika/ui"],
};

export default config;
