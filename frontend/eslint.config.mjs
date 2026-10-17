import { defineConfig, globalIgnores } from "eslint/config";
import typescript from "typescript-eslint";
import hooks from "eslint-plugin-react-hooks";

export default defineConfig([
  ...typescript.configs.recommended,
  hooks.configs.flat.recommended,
  globalIgnores([".next/**", "next-env.d.ts"]),
]);
