import {defineConfig} from "vitest/config";
export default defineConfig({test:{include:["workspace/**/*.test.ts"],environment:"node"}});
