// e2e tests create and delete real rows, so they only run against a database you
// name explicitly. The URL in .env is deliberately NOT used.
//   TEST_DATABASE_URL="postgresql://..." npm run test:e2e
process.env.DATABASE_URL =
  process.env.TEST_DATABASE_URL ??
  'postgresql://unused:unused@localhost:5432/unused';
process.env.JWT_SECRET = 'e2e-test-secret';
