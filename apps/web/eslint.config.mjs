import { FlatCompat } from "@eslint/eslintrc";

// eslint-config-next is still an eslintrc-style config, so it is bridged
// rather than rewritten. FlatCompat is the supported way to do that.
const compat = new FlatCompat({ baseDirectory: import.meta.dirname });

const config = [
  {
    ignores: [
      ".next/**",
      "node_modules/**",
      "test-results/**",
      "playwright-report/**",
    ],
  },
  ...compat.extends("next/core-web-vitals"),
  {
    rules: {
      // The verification workspace renders a presigned URL to a scan on a
      // separate origin, which next/image cannot optimize.
      "@next/next/no-img-element": "off",
    },
  },
];

export default config;
