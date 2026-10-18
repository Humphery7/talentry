import { defineConfig } from 'vitest/config';

// End-to-end tests: talk to a real Postgres. Run with `npm run test:e2e`.
export default defineConfig({
  test: {
    include: ['test/e2e/**/*.test.ts'],
    setupFiles: ['test/setup.e2e.ts'],
    testTimeout: 20_000,
    hookTimeout: 20_000,
  },
});
