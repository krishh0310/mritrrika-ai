import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTypeScript from "eslint-config-next/typescript";

const config = defineConfig([
  ...nextVitals,
  ...nextTypeScript,
  globalIgnores([
    ".next/**",
    "node_modules/**",
    "test-results/**",
    "playwright-report/**",
  ]),
  {
    rules: {
      // The verification workspace renders a presigned URL to a scan on a
      // separate origin, which next/image cannot optimize.
      "@next/next/no-img-element": "off",
    },
  },
]);

export default config;
