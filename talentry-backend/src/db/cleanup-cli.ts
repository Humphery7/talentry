// Manual run: `npm run db:cleanup`.
import { runCleanup } from './cleanup.js';
import { pool } from './pool.js';

try {
  await runCleanup();
} finally {
  await pool.end();
}
