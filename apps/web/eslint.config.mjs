import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";

export default defineConfig([
  ...nextVitals,
  {
    rules: {
      // Client-side authenticated fetching starts after gateway session restoration.
      "react-hooks/set-state-in-effect": "off",
    },
  },
  globalIgnores([".next/**", "coverage/**", "playwright-report/**", "test-results/**"]),
]);
