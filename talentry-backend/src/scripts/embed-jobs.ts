import { runMigrations } from '../db/migrate.js';
import { pool } from '../db/pool.js';
import { backfillJobEmbeddings } from '../services/jobs.service.js';

try {
  await runMigrations();
  const result = await backfillJobEmbeddings();
  console.log(
    `Jobs: found ${result.found}, embedded ${result.processed}, failed ${result.failed}`,
  );
  if (result.failed) process.exitCode = 1;
} finally {
  await pool.end();
}
