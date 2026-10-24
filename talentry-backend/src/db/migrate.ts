import { pool } from './pool.js';

/**
 * Runs on startup. Additive only: it never touches existing columns,
 * so the crawler keeps working unchanged.
 */
export async function runMigrations() {
  // Vector column for semantic matching against jobs.
  await pool.query(`CREATE EXTENSION IF NOT EXISTS vector;`);

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
  // Accounts created via Google sign-in have no password.
  await pool.query(`
    ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL;
  `);
  // Optional career details. A missing row means the user has not filled it in.
  await pool.query(`
    CREATE TABLE IF NOT EXISTS candidate_profiles (
      user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
      headline TEXT,
      current_title TEXT,
      years_experience INTEGER,
      location TEXT,
      summary TEXT,
      cv_filename TEXT,
      cv_mime TEXT,
      cv_data TEXT,
      cv_updated_at TIMESTAMPTZ,
      profile_embedding vector(384),
      embedding_updated_at TIMESTAMPTZ,
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
  `);
  // For databases that already have the table from an earlier run.
  await pool.query(`
    ALTER TABLE candidate_profiles ADD COLUMN IF NOT EXISTS cv_filename TEXT;
    ALTER TABLE candidate_profiles ADD COLUMN IF NOT EXISTS cv_mime TEXT;
    ALTER TABLE candidate_profiles ADD COLUMN IF NOT EXISTS cv_data TEXT;
    ALTER TABLE candidate_profiles ADD COLUMN IF NOT EXISTS cv_updated_at TIMESTAMPTZ;
    ALTER TABLE candidate_profiles ADD COLUMN IF NOT EXISTS profile_embedding vector(384);
    ALTER TABLE candidate_profiles ADD COLUMN IF NOT EXISTS embedding_updated_at TIMESTAMPTZ;
  `);
  await pool.query(`
    -- Numeric id for the frontend (PK stays url, crawler INSERTs are unaffected).
    ALTER TABLE jobs ADD COLUMN IF NOT EXISTS id BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE;
    -- The UNIQUE constraint already backs lookups, so drop the old extra index.
    DROP INDEX IF EXISTS idx_jobs_id;
    -- Backs the role picker's open-job counts and the role filter.
    CREATE INDEX IF NOT EXISTS idx_jobs_status_occupation ON jobs(status, occupation);
    -- Semantic search data. The crawler does not write these columns.
    ALTER TABLE jobs ADD COLUMN IF NOT EXISTS embedding vector(384);
    ALTER TABLE jobs ADD COLUMN IF NOT EXISTS embedding_updated_at TIMESTAMPTZ;
    CREATE INDEX IF NOT EXISTS idx_jobs_embedding
      ON jobs USING hnsw (embedding vector_cosine_ops);
  `);
  // Re-embed a job after the crawler changes any text that goes into its vector.
  await pool.query(`
    CREATE OR REPLACE FUNCTION clear_job_embedding() RETURNS trigger AS $$
    BEGIN
      IF NEW.title IS DISTINCT FROM OLD.title
        OR NEW.description IS DISTINCT FROM OLD.description
        OR NEW.company_slug IS DISTINCT FROM OLD.company_slug
        OR NEW.locations_json IS DISTINCT FROM OLD.locations_json
        OR NEW.employment_type IS DISTINCT FROM OLD.employment_type
        OR NEW.workplace_type IS DISTINCT FROM OLD.workplace_type
        OR NEW.seniority IS DISTINCT FROM OLD.seniority
        OR NEW.occupation IS DISTINCT FROM OLD.occupation
        OR NEW.technologies_json IS DISTINCT FROM OLD.technologies_json
      THEN
        NEW.embedding = NULL;
        NEW.embedding_updated_at = NULL;
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    DROP TRIGGER IF EXISTS jobs_clear_embedding ON jobs;
    CREATE TRIGGER jobs_clear_embedding
      BEFORE UPDATE ON jobs
      FOR EACH ROW EXECUTE FUNCTION clear_job_embedding();
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

  // Interview prep is written by talentry-career, but the API reads it here.
  // Keep this in sync with talentry-career/src/db/schema.py.
  await pool.query(`
    CREATE TABLE IF NOT EXISTS interview_attempts (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      job_id BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
      attempt_no INTEGER NOT NULL,
      status TEXT NOT NULL DEFAULT 'active',
      title TEXT NOT NULL,
      role_family TEXT NOT NULL,
      assessment_internal JSONB NOT NULL,
      assessment_public JSONB NOT NULL,
      progress JSONB NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      completed_at TIMESTAMPTZ,
      UNIQUE (user_id, job_id, attempt_no)
    );
    CREATE INDEX IF NOT EXISTS idx_interview_attempts_user_job
      ON interview_attempts (user_id, job_id);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_interview_attempts_active
      ON interview_attempts (user_id, job_id) WHERE status = 'active';
    CREATE TABLE IF NOT EXISTS interview_responses (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      attempt_id UUID NOT NULL REFERENCES interview_attempts(id) ON DELETE CASCADE,
      item_id TEXT NOT NULL,
      answer JSONB,
      score SMALLINT,
      feedback JSONB,
      completed BOOLEAN NOT NULL DEFAULT false,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE (attempt_id, item_id)
    );
    CREATE INDEX IF NOT EXISTS idx_interview_responses_attempt
      ON interview_responses (attempt_id);
  `);
}
