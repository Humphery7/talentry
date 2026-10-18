import { defineConfig } from 'vitest/config';

// Unit tests: no database needed. Run with `npm test`.
export default defineConfig({
  test: {
    include: ['test/unit/**/*.test.ts'],
    setupFiles: ['test/setup.unit.ts'],
  },
});
