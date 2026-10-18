import { pool } from './pool.js';

/**
 * Runs on startup. Additive only: it never touches existing columns,
 * so the crawler keeps working unchanged.
 */
export async function runMigrations() {
  // Sequential: applications references jobs(id), so the ALTER must land first.
  await pool.query(`
    CREATE TABLE IF NOT EXISTS users (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      name TEXT NOT NULL,
      email TEXT NOT NULL UNIQUE,
      password_hash TEXT NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
  `);
  await pool.query(`
    -- Numeric id for the frontend (PK stays url, crawler INSERTs are unaffected).
    ALTER TABLE jobs ADD COLUMN IF NOT EXISTS id BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE;
    CREATE INDEX IF NOT EXISTS idx_jobs_id ON jobs(id);
  `);
  await pool.query(`
    CREATE TABLE IF NOT EXISTS applications (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      job_id BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE (user_id, job_id)
    );
  `);
}
