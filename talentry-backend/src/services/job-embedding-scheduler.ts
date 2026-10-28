import type { PoolClient } from 'pg';
import { env } from '../config/env.js';
import { pool } from '../db/pool.js';
import { backfillJobEmbeddings } from './jobs.service.js';

// Arbitrary application-wide key. Any backend instance using the same database
// races for it, so only one runs the backfill at a time.
const LOCK_KEY = 20261025;

let timer: ReturnType<typeof setInterval> | null = null;
let running = false;

export async function runJobEmbeddingBackfill() {
  if (running) return;
  running = true;

  let client: PoolClient | null = null;
  let locked = false;

  try {
    client = await pool.connect();
    const { rows } = await client.query<{ locked: boolean }>(
      'SELECT pg_try_advisory_lock($1) AS locked',
      [LOCK_KEY],
    );
    locked = rows[0]?.locked ?? false;
    if (!locked) return;

    const result = await backfillJobEmbeddings();
    if (result.found) {
      console.log(
        `Job embeddings: embedded ${result.processed}/${result.found}` +
          (result.failed ? `, failed ${result.failed}` : ''),
      );
    }
  } catch (err) {
    console.error('Job embedding backfill failed:', err);
  } finally {
    if (client) {
      if (locked) {
        await client
          .query('SELECT pg_advisory_unlock($1)', [LOCK_KEY])
          .catch(() => {});
      }
      client.release();
    }
    running = false;
  }
}

/**
 * Runs the incremental job embedding backfill once at startup, then on an
 * interval. Set EMBED_JOBS_INTERVAL_MINUTES=0 to disable the schedule.
 */
export function startJobEmbeddingSchedule() {
  const minutes = env.embedJobsIntervalMinutes;
  if (!Number.isFinite(minutes) || minutes <= 0) {
    console.log('Job embedding schedule disabled.');
    return;
  }

  void runJobEmbeddingBackfill();
  timer = setInterval(
    () => void runJobEmbeddingBackfill(),
    minutes * 60_000,
  );
  timer.unref();
  console.log(`Job embeddings: backfilling every ${minutes} minute(s).`);
}

export function stopJobEmbeddingSchedule() {
  if (!timer) return;
  clearInterval(timer);
  timer = null;
}
