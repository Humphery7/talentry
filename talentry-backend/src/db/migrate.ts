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
      phone TEXT,
      linkedin_url TEXT,
      github_url TEXT,
      website_url TEXT,
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
    ALTER TABLE candidate_profiles ADD COLUMN IF NOT EXISTS phone TEXT;
    ALTER TABLE candidate_profiles ADD COLUMN IF NOT EXISTS linkedin_url TEXT;
    ALTER TABLE candidate_profiles ADD COLUMN IF NOT EXISTS github_url TEXT;
    ALTER TABLE candidate_profiles ADD COLUMN IF NOT EXISTS website_url TEXT;
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
    -- Semantic search data. The crawler writes these with each job.
    ALTER TABLE jobs ADD COLUMN IF NOT EXISTS embedding vector(384);
    ALTER TABLE jobs ADD COLUMN IF NOT EXISTS embedding_text_hash TEXT;
    ALTER TABLE jobs ADD COLUMN IF NOT EXISTS embedding_updated_at TIMESTAMPTZ;
    CREATE INDEX IF NOT EXISTS idx_jobs_embedding
      ON jobs USING hnsw (embedding vector_cosine_ops);
  `);
  // The crawler owns job embeddings now and writes them with the job row.
  await pool.query(`
    DROP TRIGGER IF EXISTS jobs_clear_embedding ON jobs;
    DROP FUNCTION IF EXISTS clear_job_embedding() CASCADE;
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

  // Recommendations are written by talentry-career, but the API reads them here.
  // Keep this in sync with talentry-career/src/db/schema.py.
  await pool.query(`
    CREATE TABLE IF NOT EXISTS job_recommendations (
      user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      job_id BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
      rank INTEGER NOT NULL,
      score DOUBLE PRECISION NOT NULL,
      similarity DOUBLE PRECISION,
      reason TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      PRIMARY KEY (user_id, job_id)
    );
    CREATE INDEX IF NOT EXISTS idx_job_recommendations_user_rank
      ON job_recommendations (user_id, rank);
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

  // Application agent. talentry-career owns the worker and writes most of this;
  // the API reads progress and records the user's answers, edits and approval.
  // Keep this in sync with talentry-career/src/db/schema.py.
  await pool.query(`
    CREATE TABLE IF NOT EXISTS agent_applications (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      batch_id UUID NOT NULL,
      user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      job_id BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
      status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN (
          'queued', 'in_progress', 'needs_input', 'pending_approval',
          'approved', 'submitting', 'submitted', 'unconfirmed', 'failed',
          'cancelled'
        )),
      platform TEXT,
      apply_url TEXT,
      options JSONB NOT NULL DEFAULT '{}'::jsonb,
      plan JSONB NOT NULL DEFAULT '{}'::jsonb,
      attention JSONB NOT NULL DEFAULT '[]'::jsonb,
      warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
      browser_state JSONB,
      approved_snapshot JSONB,
      approved_at TIMESTAMPTZ,
      submitted_at TIMESTAMPTZ,
      result JSONB,
      screenshot TEXT,
      attempts INTEGER NOT NULL DEFAULT 0,
      error TEXT,
      heartbeat_at TIMESTAMPTZ,
      run_after TIMESTAMPTZ,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      started_at TIMESTAMPTZ,
      completed_at TIMESTAMPTZ,
      UNIQUE (batch_id, job_id)
    );
    CREATE INDEX IF NOT EXISTS idx_agent_applications_status
      ON agent_applications (status, created_at);
    CREATE INDEX IF NOT EXISTS idx_agent_applications_user
      ON agent_applications (user_id, created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_agent_applications_queue
      ON agent_applications (status, run_after, created_at);

    CREATE TABLE IF NOT EXISTS agent_application_documents (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      agent_application_id UUID NOT NULL
        REFERENCES agent_applications(id) ON DELETE CASCADE,
      kind TEXT NOT NULL,
      version INTEGER NOT NULL,
      content TEXT NOT NULL,
      origin TEXT NOT NULL,
      notes JSONB NOT NULL DEFAULT '[]'::jsonb,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE (agent_application_id, kind, version)
    );

    CREATE TABLE IF NOT EXISTS agent_application_events (
      id BIGSERIAL PRIMARY KEY,
      agent_application_id UUID NOT NULL
        REFERENCES agent_applications(id) ON DELETE CASCADE,
      kind TEXT NOT NULL,
      message TEXT NOT NULL,
      data JSONB,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS idx_agent_application_events_app
      ON agent_application_events (agent_application_id, id);

    CREATE TABLE IF NOT EXISTS applicant_answers (
      user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      question_key TEXT NOT NULL,
      question TEXT NOT NULL,
      answer TEXT NOT NULL,
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      PRIMARY KEY (user_id, question_key)
    );

    CREATE TABLE IF NOT EXISTS notifications (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      agent_application_id UUID
        REFERENCES agent_applications(id) ON DELETE CASCADE,
      kind TEXT NOT NULL,
      title TEXT NOT NULL,
      body TEXT NOT NULL DEFAULT '',
      read_at TIMESTAMPTZ,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS idx_notifications_user
      ON notifications (user_id, created_at DESC);
  `);

  // One agent application per user and job. Retrying or cancelling updates the
  // existing row instead of creating another one.
  try {
    await pool.query(`
      CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_applications_user_job
        ON agent_applications (user_id, job_id);
    `);
  } catch (err) {
    // An existing database with duplicate rows cannot get the index until they
    // are cleaned up. The enqueue check still prevents new duplicates.
    if ((err as { code?: string }).code !== '23505') throw err;
    console.warn(
      'Could not add agent_applications unique index: duplicate rows exist.',
    );
  }
}
