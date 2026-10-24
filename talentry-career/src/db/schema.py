import psycopg

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS job_recommendations (
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  job_id BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  rank INTEGER NOT NULL,
  score DOUBLE PRECISION NOT NULL,
  similarity DOUBLE PRECISION,
  reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, job_id)
)
"""

ADD_COLUMNS = """
ALTER TABLE job_recommendations ADD COLUMN IF NOT EXISTS similarity DOUBLE PRECISION;
ALTER TABLE job_recommendations ADD COLUMN IF NOT EXISTS reason TEXT;
"""

CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_job_recommendations_user_rank
  ON job_recommendations (user_id, rank)
"""

# Interview prep. The Express backend creates the same tables so it can read
# them; both use IF NOT EXISTS and this service is the writer.
CREATE_INTERVIEW_ATTEMPTS = """
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
)
"""

CREATE_INTERVIEW_RESPONSES = """
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
)
"""

CREATE_INTERVIEW_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_interview_attempts_user_job
  ON interview_attempts (user_id, job_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_interview_attempts_active
  ON interview_attempts (user_id, job_id) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_interview_responses_attempt
  ON interview_responses (attempt_id);
"""


def ensure_schema(conn: psycopg.Connection) -> None:
    conn.execute(CREATE_TABLE)
    conn.execute(ADD_COLUMNS)
    conn.execute(CREATE_INDEX)
    conn.execute(CREATE_INTERVIEW_ATTEMPTS)
    conn.execute(CREATE_INTERVIEW_RESPONSES)
    conn.execute(CREATE_INTERVIEW_INDEXES)
