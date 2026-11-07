// Keeps the database from growing without bound.
//
// Everything here is deliberately conservative: it only touches content that
// is already old and no longer useful, and it never removes a job someone can
// still apply to. Jobs that users applied to are kept forever (only their heavy
// description/embedding payloads are cleared).
import { pool } from './pool.js';

const CLOSED_DELETE_DAYS = 7; // closed jobs are removed after a short grace
const CLOSED_HEAVY_DAYS = 7; // ...and keep only a slim row if referenced
const STALE_OPEN_DAYS = 90; // open jobs the crawler has not seen in 90 days
const CRAWLER_ALIVE_DAYS = 7; // only prune stale open jobs while crawling works
const NOTIFICATION_DAYS = 60; // delete read notifications
const EVENT_DAYS = 90; // delete events for finished applications
const SCREENSHOT_DAYS = 90; // drop screenshots/browser state for finished apps

const RUN_EVERY_MS = 24 * 60 * 60 * 1000;
const FIRST_RUN_MS = 2 * 60 * 1000;

interface Counts {
  jobsSlimmed: number;
  jobsDeleted: number;
  notificationsDeleted: number;
  eventsDeleted: number;
  applicationsShrunk: number;
}

/**
 * Delete or shrink old rows. Safe to run repeatedly.
 * A failure in one step is logged and does not stop the others.
 */
export async function runCleanup(): Promise<Counts> {
  const counts: Counts = {
    jobsSlimmed: 0,
    jobsDeleted: 0,
    notificationsDeleted: 0,
    eventsDeleted: 0,
    applicationsShrunk: 0,
  };

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
      counts.notificationsDeleted +
      counts.eventsDeleted +
      counts.applicationsShrunk >
    0;

  if (changed) {
    console.log('DB cleanup:', counts);
  }

  // VACUUM cannot run inside a transaction. It lets Postgres reuse the space
  // freed above instead of only marking rows dead.
  if (changed) {
    try {
      await pool.query(
        'VACUUM (ANALYZE) jobs, notifications, agent_applications, agent_application_events',
      );
    } catch (err) {
      console.error('DB cleanup: vacuum failed:', err);
    }
  }

  return counts;
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
