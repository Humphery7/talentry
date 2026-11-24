// Keeps the database from growing without bound.
//
// Everything here is deliberately conservative: it only touches content that
// is already old and no longer useful, and it never removes a job someone can
// still apply to. Jobs that users applied to are kept forever (only their heavy
// description/embedding payloads are cleared).
import { pool } from './pool.js';

// One day, not zero: closing is inferred from a job missing on one crawl, and
// the next day's crawl reopens it. Immediate deletion would drop job ids and
// force a re-insert (and re-embed) whenever a board has a bad day.
const CLOSED_DELETE_DAYS = 1; // closed jobs are removed after a short grace
const CLOSED_HEAVY_DAYS = 1; // ...and keep only a slim row if referenced
const STALE_OPEN_DAYS = 30; // open jobs the crawler has not seen in 30 days
const CRAWLER_ALIVE_DAYS = 7; // only prune stale open jobs while crawling works
const CANCELLED_DELETE_HOURS = 24; // cancelled applications
const SUBMITTED_RETAIN_DAYS = 30; // keep submitted docs/details this long, then only the reference
const NOTIFICATION_DAYS = 30; // delete read notifications
const EVENT_DAYS = 30; // delete events for other finished applications
const SCREENSHOT_DAYS = 30; // drop screenshots/browser state for other finished apps

// Mirrors `classify()` in talentry-career/src/services/agent_applications/
// facts.py. Kept here so old rows can be removed even though the career
// service no longer writes them.
const SENSITIVE_QUESTION = [
  'authori[sz]ed to work|work authori[sz]ation|right to work|work permit',
  'work visa|\\mvisa\\M|sponsor|immigration|citizen|nationality',
  'salary|compensation|expected pay|desired rate|remuneration',
  'notice period|start date|available to start|relocat',
  'convict|criminal|felony|background check|drug test|conflict of interest',
  'non-?compete|restrictive covenant|gdpr|privacy policy|under oath',
  'gender|racial|ethnic|veteran|disabilit|sexual orientation|religion',
  'marital|date of birth|self-identif|equal opportunity|\\meeo\\M',
].join('|');

const RUN_EVERY_MS = 24 * 60 * 60 * 1000;
const FIRST_RUN_MS = 2 * 60 * 1000;

// ---- keeping the `jobs` table from growing without bound ----------------
//
// Deleting rows does not shrink a Postgres table: the space is only marked
// reusable inside the file, and Neon bills the file. The crawler also rewrites
// last_seen_at for every job it sees, which leaves a dead row version behind
// each time. So the table is rewritten (VACUUM FULL) once bloat is worth the
// lock. That is the only operation that hands the space back to Neon.
//
// There is deliberately no content-based dedupe: boards routinely publish
// different requisitions with the same title and boilerplate description
// (Accenture, for example, had 55 distinct job ids under one title), so
// matching on text deletes real jobs. The crawler already upserts by URL.
const JOBS_INDEX = 'idx_jobs_embedding';
const JOBS_INDEX_SQL =
  'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jobs_embedding ' +
  'ON jobs USING hnsw (embedding vector_cosine_ops)';
// Rewrite only when the table is this much bigger than it should be, and at
// most this often (a rewrite locks `jobs` for a minute or two).
const REWRITE_MIN_GROWTH = 96 * 1024 * 1024;
const REWRITE_GROWTH_RATIO = 1.35;
const REWRITE_MIN_INTERVAL_MS = 6 * 24 * 60 * 60 * 1000;
// The free space Neon gives this project, and the slack kept for other tables.
const STORAGE_LIMIT_BYTES =
  Number(process.env.DB_STORAGE_LIMIT_MB ?? 1000) * 1024 * 1024;
const REWRITE_HEADROOM_BYTES = 32 * 1024 * 1024;

interface Counts {
  jobsSlimmed: number;
  jobsDeleted: number;
  jobsRewritten: number;
  applicationsDeleted: number;
  documentsDeleted: number;
  applicationsCleared: number;
  notificationsDeleted: number;
  eventsDeleted: number;
  applicationsShrunk: number;
  answersDeleted: number;
}

/**
 * Delete or shrink old rows. Safe to run repeatedly.
 * A failure in one step is logged and does not stop the others.
 */
export async function runCleanup(): Promise<Counts> {
  const counts: Counts = {
    jobsSlimmed: 0,
    jobsDeleted: 0,
    jobsRewritten: 0,
    applicationsDeleted: 0,
    documentsDeleted: 0,
    applicationsCleared: 0,
    notificationsDeleted: 0,
    eventsDeleted: 0,
    applicationsShrunk: 0,
    answersDeleted: 0,
  };

  // A cancelled application is only useful as a short-lived receipt. Removing
  // it also stops it from pinning a job that would otherwise be cleaned up.
  await step('agent applications: delete cancelled', counts, async () => {
    const { rowCount } = await pool.query(
      `DELETE FROM agent_applications
       WHERE status = 'cancelled'
         AND updated_at < now() - make_interval(hours => $1)`,
      [CANCELLED_DELETE_HOURS],
    );
    counts.applicationsDeleted = rowCount ?? 0;
  });

  // Sensitive answers (work authorization, salary, legal declarations and so
  // on) are stored on the application only, never in the answer bank: the
  // right answer changes with the job and the country. This removes anything
  // saved by earlier versions. The pattern mirrors `classify()` in the career
  // service's facts.py.
  await step('applicant answers: delete sensitive', counts, async () => {
    const { rowCount } = await pool.query(
      `DELETE FROM applicant_answers
       WHERE question ~* $1`,
      [SENSITIVE_QUESTION],
    );
    counts.answersDeleted = rowCount ?? 0;
  });

  // A submitted application is kept as a permanent "already applied" record,
  // but the generated CV/cover letter and the filled-in form details are only
  // useful for a short review window. After that the row keeps the reference
  // (user, job, status, submitted date) and nothing else.
  await step('agent documents: delete old submitted files', counts, async () => {
    const { rowCount } = await pool.query(
      `DELETE FROM agent_application_documents d
       USING agent_applications a
       WHERE d.agent_application_id = a.id
         AND a.status = 'submitted'
         AND COALESCE(a.completed_at, a.submitted_at, a.updated_at)
             < now() - make_interval(days => $1)`,
      [SUBMITTED_RETAIN_DAYS],
    );
    counts.documentsDeleted = rowCount ?? 0;
  });

  await step('agent applications: keep only the submitted reference', counts, async () => {
    const { rowCount } = await pool.query(
      `UPDATE agent_applications
       SET plan = '{}'::jsonb,
           attention = '[]'::jsonb,
           warnings = '[]'::jsonb,
           options = '{}'::jsonb,
           approved_snapshot = NULL,
           browser_state = NULL,
           screenshot = NULL,
           result = NULL,
           error = NULL
       WHERE status = 'submitted'
         AND COALESCE(completed_at, submitted_at, updated_at)
             < now() - make_interval(days => $1)
         AND (
           plan <> '{}'::jsonb
           OR attention <> '[]'::jsonb
           OR warnings <> '[]'::jsonb
           OR options <> '{}'::jsonb
           OR approved_snapshot IS NOT NULL
           OR browser_state IS NOT NULL
           OR screenshot IS NOT NULL
           OR result IS NOT NULL
           OR error IS NOT NULL
         )`,
      [SUBMITTED_RETAIN_DAYS],
    );
    counts.applicationsCleared = rowCount ?? 0;
  });

  await step('agent events: delete old submitted history', counts, async () => {
    const { rowCount } = await pool.query(
      `DELETE FROM agent_application_events e
       USING agent_applications a
       WHERE e.agent_application_id = a.id
         AND a.status = 'submitted'
         AND e.created_at < now() - make_interval(days => $1)`,
      [SUBMITTED_RETAIN_DAYS],
    );
    counts.eventsDeleted += rowCount ?? 0;
  });

  await step('notifications: delete old submitted items', counts, async () => {
    const { rowCount } = await pool.query(
      `DELETE FROM notifications n
       USING agent_applications a
       WHERE n.agent_application_id = a.id
         AND a.status = 'submitted'
         AND COALESCE(a.completed_at, a.submitted_at, a.updated_at)
             < now() - make_interval(days => $1)`,
      [SUBMITTED_RETAIN_DAYS],
    );
    counts.notificationsDeleted += rowCount ?? 0;
  });

  // Only prune "open" jobs when the crawler is still working. Otherwise a long
  // crawler outage would make every job look stale and wipe the board.
  const crawlerActive = await isCrawlerActive();

  // Closed jobs nobody applied to, saved or interviewed for are just dead
  // weight. A short grace period lets a job that briefly disappeared return.
  await step('jobs: delete old unreferenced jobs', counts, async () => {
    const { rowCount } = await pool.query(
      `DELETE FROM jobs j
       WHERE (
           (j.status = 'closed'
            AND CASE WHEN j.closed_at ~ '^[0-9]{4}-'
                     THEN j.closed_at::timestamptz END
                < now() - make_interval(days => $1))
           OR
           ($2::boolean
            AND j.status = 'open'
            AND j.last_seen_at::timestamptz
                < now() - make_interval(days => $3))
         )
         AND NOT EXISTS (SELECT 1 FROM applications a WHERE a.job_id = j.id)
         AND NOT EXISTS (SELECT 1 FROM agent_applications a WHERE a.job_id = j.id)
         AND NOT EXISTS (SELECT 1 FROM interview_attempts i WHERE i.job_id = j.id)`,
      [CLOSED_DELETE_DAYS, crawlerActive, STALE_OPEN_DAYS],
    );
    counts.jobsDeleted = rowCount ?? 0;
  });

  // Jobs that do have user history stay, because deleting them would cascade
  // into that history. They only lose their heavy payload.
  await step('jobs: clear old payloads', counts, async () => {
    const { rowCount } = await pool.query(
      `UPDATE jobs
       SET description = NULL,
           embedding = NULL,
           embedding_text_hash = NULL,
           embedding_updated_at = NULL
       WHERE (
           (status = 'closed'
            AND CASE WHEN closed_at ~ '^[0-9]{4}-'
                     THEN closed_at::timestamptz END
                < now() - make_interval(days => $1))
           OR
           ($2::boolean
            AND status = 'open'
            AND last_seen_at::timestamptz
                < now() - make_interval(days => $3))
         )
         AND (description IS NOT NULL OR embedding IS NOT NULL
              OR embedding_text_hash IS NOT NULL)`,
      [CLOSED_HEAVY_DAYS, crawlerActive, STALE_OPEN_DAYS],
    );
    counts.jobsSlimmed = rowCount ?? 0;
  });

  // Give the space from deleted and rewritten rows back to Neon. This is the
  // only step that shrinks the database file; a plain VACUUM only reuses space
  // internally.
  await step('jobs: reclaim bloat', counts, async () => {
    const size = await pool.query<{ bytes: string; rows: string }>(
      `SELECT pg_total_relation_size('jobs')::text AS bytes,
              (SELECT count(*) FROM jobs)::text AS rows`,
    );
    const sizeBytes = Number(size.rows[0]?.bytes ?? 0);
    const rows = Number(size.rows[0]?.rows ?? 0);
    if (!rows) return;

    const state = await readMaintenanceState();
    const last = state.get('jobs_rewrite_at');
    const baselineBytes = Number(state.get('jobs_rewrite_bytes') ?? 0) || null;
    const baselineRows = Number(state.get('jobs_rewrite_rows') ?? 0) || null;
    if (
      !shouldRewriteJobs({
        sizeBytes,
        rows,
        baselineBytes,
        baselineRows,
        lastRewriteAt: last ? new Date(last) : null,
      })
    ) {
      return;
    }

    let droppedIndex = false;
    let rewritten = false;
    try {
      if (!rewriteFits(await databaseBytes(), sizeBytes)) {
        // A rewrite needs room for the compact copy while the old one still
        // exists. The embedding index is the largest thing we can free, and it
        // is rebuilt straight after.
        console.log(
          'DB cleanup: freeing the embedding index to make room for the rewrite.',
        );
        await pool.query(`DROP INDEX IF EXISTS ${JOBS_INDEX}`);
        droppedIndex = true;
      }
      if (!rewriteFits(await databaseBytes(), sizeBytes)) {
        console.warn(
          'DB cleanup: not enough free space to rewrite jobs; skipping this run.',
        );
        return;
      }

      // Keep the lock short. If a reader holds the table, try again tomorrow
      // rather than queueing every request behind the rewrite.
      const client = await pool.connect();
      try {
        await client.query(`SET lock_timeout = '20s'`);
        await client.query('VACUUM (FULL, ANALYZE) jobs');
      } finally {
        client.release();
      }
      counts.jobsRewritten = 1;
      rewritten = true;
    } finally {
      if (droppedIndex) await ensureJobsIndex();
    }

    // Record the baseline only once the index is back, so the next comparison
    // is like for like (otherwise the rebuilt index looks like fresh bloat).
    if (rewritten) {
      const compact = await pool.query<{ bytes: string }>(
        `SELECT pg_total_relation_size('jobs')::text AS bytes`,
      );
      await writeMaintenanceState({
        jobs_rewrite_at: new Date().toISOString(),
        jobs_rewrite_bytes: String(Number(compact.rows[0]?.bytes ?? sizeBytes)),
        jobs_rewrite_rows: String(rows),
      });
    }
  });

  await step('notifications: delete old read items', counts, async () => {
    const { rowCount } = await pool.query(
      `DELETE FROM notifications
       WHERE read_at IS NOT NULL
         AND created_at < now() - make_interval(days => $1)`,
      [NOTIFICATION_DAYS],
    );
    counts.notificationsDeleted = rowCount ?? 0;
  });

  // Active applications keep their event history; finished ones do not need it.
  await step('agent events: delete old finished history', counts, async () => {
    const { rowCount } = await pool.query(
      `DELETE FROM agent_application_events e
       USING agent_applications a
       WHERE e.agent_application_id = a.id
         AND e.created_at < now() - make_interval(days => $1)
         AND a.status IN
           ('submitted', 'unconfirmed', 'failed', 'cancelled')`,
      [EVENT_DAYS],
    );
    counts.eventsDeleted = rowCount ?? 0;
  });

  // Screenshots and browser session state are the largest columns on an
  // application. Once it is finished and old, neither is needed.
  await step('agent applications: drop old screenshots/state', counts, async () => {
    const { rowCount } = await pool.query(
      `UPDATE agent_applications
       SET screenshot = NULL,
           browser_state = NULL
       WHERE status IN ('submitted', 'unconfirmed', 'failed', 'cancelled')
         AND completed_at < now() - make_interval(days => $1)
         AND (screenshot IS NOT NULL OR browser_state IS NOT NULL)`,
      [SCREENSHOT_DAYS],
    );
    counts.applicationsShrunk = rowCount ?? 0;
  });

  const changed =
    counts.jobsSlimmed +
    counts.jobsDeleted +
    counts.jobsRewritten +
    counts.applicationsDeleted +
    counts.documentsDeleted +
    counts.applicationsCleared +
    counts.notificationsDeleted +
    counts.eventsDeleted +
    counts.applicationsShrunk +
    counts.answersDeleted >
    0;

  if (changed) {
    console.log('DB cleanup:', counts);
  }

  // VACUUM cannot run inside a transaction. It lets Postgres reuse the space
  // freed above instead of only marking rows dead.
  if (changed) {
    try {
      await pool.query(
        'VACUUM (ANALYZE) jobs, notifications, agent_applications, agent_application_documents, agent_application_events, applicant_answers',
      );
    } catch (err) {
      console.error('DB cleanup: vacuum failed:', err);
    }
  }

  return counts;
}

// ---- bloat bookkeeping --------------------------------------------------

export interface RewriteCheck {
  sizeBytes: number;
  rows: number;
  /** Size and row count right after the last rewrite, if there was one. */
  baselineBytes: number | null;
  baselineRows: number | null;
  lastRewriteAt: Date | null;
}

/**
 * Whether rewriting `jobs` is likely to give back real space.
 *
 * Growth is measured per row, so simply crawling more jobs never looks like
 * bloat. The first run has no baseline and rewrites any table big enough to
 * plausibly hold dead space; afterwards the interval and the per-row growth
 * test keep a rewrite rare.
 */
export function shouldRewriteJobs(check: RewriteCheck): boolean {
  const { sizeBytes, rows, baselineBytes, baselineRows, lastRewriteAt } = check;
  if (rows <= 0 || sizeBytes <= 0) return false;

  if (lastRewriteAt) {
    const age = Date.now() - lastRewriteAt.getTime();
    // A bad timestamp means "unknown", which must not block a needed rewrite.
    if (Number.isFinite(age) && age < REWRITE_MIN_INTERVAL_MS) return false;
  }

  if (!baselineBytes || !baselineRows) {
    return sizeBytes >= REWRITE_MIN_GROWTH;
  }

  const expectedBytes = baselineBytes * (rows / baselineRows);
  const growth = sizeBytes - expectedBytes;
  return (
    growth >= REWRITE_MIN_GROWTH &&
    sizeBytes >= expectedBytes * REWRITE_GROWTH_RATIO
  );
}

/**
 * A rewrite needs room for the compact copy while the old table still exists,
 * or the write fails and Neon reports a storage limit error. The copy is
 * assumed to be a little over half the current table (live rows compress
 * well); the rest is slack for WAL and the other tables.
 */
export function rewriteFits(
  databaseBytes: number,
  tableBytes: number,
): boolean {
  if (databaseBytes <= 0 || tableBytes <= 0) return false;
  const copyBytes = Math.round(tableBytes * 0.55);
  return (
    databaseBytes + copyBytes + REWRITE_HEADROOM_BYTES <= STORAGE_LIMIT_BYTES
  );
}

async function readMaintenanceState(): Promise<Map<string, string>> {
  try {
    const { rows } = await pool.query<{ key: string; value: string }>(
      'SELECT key, value FROM maintenance_state',
    );
    return new Map(rows.map((r) => [r.key, r.value]));
  } catch (err) {
    // The migration may not have run yet; treat that as "no history".
    console.error('DB cleanup: could not read maintenance state:', err);
    return new Map();
  }
}

async function writeMaintenanceState(
  values: Record<string, string>,
): Promise<void> {
  const keys = Object.keys(values);
  try {
    await pool.query(
      `INSERT INTO maintenance_state (key, value, updated_at)
       SELECT k, v, now() FROM unnest($1::text[], $2::text[]) AS t(k, v)
       ON CONFLICT (key)
       DO UPDATE SET value = EXCLUDED.value, updated_at = now()`,
      [keys, keys.map((k) => values[k])],
    );
  } catch (err) {
    console.error('DB cleanup: could not write maintenance state:', err);
  }
}

async function databaseBytes(): Promise<number> {
  try {
    const { rows } = await pool.query<{ bytes: string }>(
      `SELECT pg_database_size(current_database())::text AS bytes`,
    );
    return Number(rows[0]?.bytes ?? 0);
  } catch (err) {
    console.error('DB cleanup: could not measure database size:', err);
    return 0;
  }
}

/**
 * Rebuild the vector index after it was dropped to make room. The career
 * service can still match without it, only more slowly, so a failure here is
 * logged rather than thrown.
 */
async function ensureJobsIndex(): Promise<void> {
  try {
    const { rows } = await pool.query<{ present: boolean }>(
      `SELECT to_regclass($1) IS NOT NULL AS present`,
      [JOBS_INDEX],
    );
    if (rows[0]?.present) return;
    console.log('DB cleanup: rebuilding the jobs embedding index.');
    await pool.query(JOBS_INDEX_SQL);
  } catch (err) {
    console.error(
      'DB cleanup: could not rebuild the jobs embedding index:',
      err,
    );
  }
}

async function isCrawlerActive(): Promise<boolean> {
  try {
    const { rows } = await pool.query<{ latest: Date | null }>(
      `SELECT max(last_seen_at::timestamptz) AS latest FROM jobs`,
    );
    const latest = rows[0]?.latest;
    if (latest == null) return false;
    return (
      Date.now() - new Date(latest).getTime() <
      CRAWLER_ALIVE_DAYS * 24 * 60 * 60 * 1000
    );
  } catch (err) {
    // Never delete open jobs just because this check failed.
    console.error('DB cleanup: could not check crawler activity:', err);
    return false;
  }
}

async function step(
  name: string,
  counts: Counts,
  fn: () => Promise<void>,
): Promise<void> {
  try {
    await fn();
  } catch (err) {
    console.error(`DB cleanup failed (${name}):`, err);
  }
}

/** Run once shortly after boot, then once a day. */
export function startCleanupSchedule(): void {
  const run = () => {
    void runCleanup().catch((err) => console.error('DB cleanup failed:', err));
  };
  setTimeout(run, FIRST_RUN_MS).unref();
  setInterval(run, RUN_EVERY_MS).unref();
}
