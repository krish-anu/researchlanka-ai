import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

/**
 * Node by default; component tests opt into jsdom.
 *
 * Most of what is worth testing here is pure — formatting, URL building, the
 * role and capability rules, session signing — and runs far faster in Node than
 * under a simulated DOM. The few files that render components declare
 * `@vitest-environment jsdom` in a docblock, so only they pay for it.
 */
export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
    // Spelled out because an aliased import of a component (`.tsx`) does not
    // resolve on the defaults here, while an aliased `.ts` module does.
    extensions: [".ts", ".tsx", ".js", ".jsx", ".mjs", ".json"],
  },
  // The app's tsconfig keeps JSX preserved for Next. Vitest/Vite still needs
  // to lower TSX during tests so Rolldown can parse component test files.
  oxc: {
    jsx: {
      runtime: "automatic",
      importSource: "react",
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.{ts,tsx}"],
    globals: true,
    coverage: {
      provider: "v8",
      include: ["src/services/**/*.ts", "src/components/**/*.tsx"],
      reporter: ["text-summary"],
    },
  },
});
