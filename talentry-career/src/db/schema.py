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

AGENT_STATUSES = (
    "queued",
    "in_progress",
    "needs_input",
    "pending_approval",
    "approved",
    "submitting",
    "submitted",
    "unconfirmed",
    "failed",
    "cancelled",
)
_AGENT_STATUS_SQL = ", ".join(f"'{status}'" for status in AGENT_STATUSES)

CREATE_AGENT_APPLICATIONS = f"""
CREATE TABLE IF NOT EXISTS agent_applications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  batch_id UUID NOT NULL,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  job_id BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'queued'
    CHECK (status IN ({_AGENT_STATUS_SQL})),
  platform TEXT,
  apply_url TEXT,
  options JSONB NOT NULL DEFAULT '{{}}'::jsonb,
  plan JSONB NOT NULL DEFAULT '{{}}'::jsonb,
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
)
"""

ALTER_AGENT_APPLICATIONS = f"""
ALTER TABLE agent_applications ADD COLUMN IF NOT EXISTS platform TEXT;
ALTER TABLE agent_applications ADD COLUMN IF NOT EXISTS apply_url TEXT;
ALTER TABLE agent_applications ADD COLUMN IF NOT EXISTS options JSONB NOT NULL DEFAULT '{{}}'::jsonb;
ALTER TABLE agent_applications ADD COLUMN IF NOT EXISTS plan JSONB NOT NULL DEFAULT '{{}}'::jsonb;
ALTER TABLE agent_applications ADD COLUMN IF NOT EXISTS attention JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE agent_applications ADD COLUMN IF NOT EXISTS warnings JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE agent_applications ADD COLUMN IF NOT EXISTS browser_state JSONB;
ALTER TABLE agent_applications ADD COLUMN IF NOT EXISTS approved_snapshot JSONB;
ALTER TABLE agent_applications ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ;
ALTER TABLE agent_applications ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMPTZ;
ALTER TABLE agent_applications ADD COLUMN IF NOT EXISTS screenshot TEXT;
ALTER TABLE agent_applications ADD COLUMN IF NOT EXISTS result JSONB;
ALTER TABLE agent_applications ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE agent_applications ADD COLUMN IF NOT EXISTS heartbeat_at TIMESTAMPTZ;
ALTER TABLE agent_applications ADD COLUMN IF NOT EXISTS run_after TIMESTAMPTZ;
ALTER TABLE agent_applications ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ;
ALTER TABLE agent_applications ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;
ALTER TABLE agent_applications DROP CONSTRAINT IF EXISTS agent_applications_status_check;
ALTER TABLE agent_applications ADD CONSTRAINT agent_applications_status_check
  CHECK (status IN ({_AGENT_STATUS_SQL}));
"""

CREATE_AGENT_APPLICATION_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_agent_applications_status
  ON agent_applications (status, created_at);
CREATE INDEX IF NOT EXISTS idx_agent_applications_user
  ON agent_applications (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_applications_queue
  ON agent_applications (status, run_after, created_at);
"""

CREATE_AGENT_APPLICATION_DOCUMENTS = """
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
)
"""

CREATE_AGENT_APPLICATION_EVENTS = """
CREATE TABLE IF NOT EXISTS agent_application_events (
  id BIGSERIAL PRIMARY KEY,
  agent_application_id UUID NOT NULL
    REFERENCES agent_applications(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  message TEXT NOT NULL,
  data JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

CREATE_APPLICANT_ANSWERS = """
CREATE TABLE IF NOT EXISTS applicant_answers (
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  question_key TEXT NOT NULL,
  question TEXT NOT NULL,
  answer TEXT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, question_key)
)
"""

CREATE_NOTIFICATIONS = """
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
)
"""

CREATE_AGENT_APPLICATION_CHILD_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_agent_application_events_app
  ON agent_application_events (agent_application_id, id);
CREATE INDEX IF NOT EXISTS idx_notifications_user
  ON notifications (user_id, created_at DESC);
"""


def ensure_schema(conn: psycopg.Connection) -> None:
    conn.execute(CREATE_TABLE)
    conn.execute(ADD_COLUMNS)
    conn.execute(CREATE_INDEX)
    conn.execute(CREATE_INTERVIEW_ATTEMPTS)
    conn.execute(CREATE_INTERVIEW_RESPONSES)
    conn.execute(CREATE_INTERVIEW_INDEXES)
    conn.execute(CREATE_AGENT_APPLICATIONS)
    conn.execute(ALTER_AGENT_APPLICATIONS)
    conn.execute(CREATE_AGENT_APPLICATION_INDEXES)
    conn.execute(CREATE_AGENT_APPLICATION_DOCUMENTS)
    conn.execute(CREATE_AGENT_APPLICATION_EVENTS)
    conn.execute(CREATE_APPLICANT_ANSWERS)
    conn.execute(CREATE_NOTIFICATIONS)
    conn.execute(CREATE_AGENT_APPLICATION_CHILD_INDEXES)
