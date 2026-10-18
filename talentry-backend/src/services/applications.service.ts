import { pool } from '../db/pool.js';
import { HttpError } from '../utils/http-error.js';

/** Postgres error code for "unique constraint violated". */
const UNIQUE_VIOLATION = '23505';

export async function apply(userId: string, jobId: number) {
  const job = await pool.query('SELECT id FROM jobs WHERE id = $1', [jobId]);
  if (!job.rowCount) throw new HttpError(409, 'Job does not exist.');

  try {
    const { rows } = await pool.query(
      'INSERT INTO applications (user_id, job_id) VALUES ($1, $2) RETURNING id, job_id AS "jobId", created_at AS "createdAt"',
      [userId, jobId],
    );
    return { ok: true, ...rows[0] };
  } catch (err) {
    // Applying twice to the same job is not an error: answer "ok" and flag it.
    if ((err as { code?: string }).code === UNIQUE_VIOLATION) {
      return { ok: true, jobId, duplicate: true };
    }
    throw err;
  }
}

export async function listForUser(userId: string) {
  const { rows } = await pool.query(
    `SELECT a.job_id AS "jobId", j.title, c.name AS company, a.created_at AS "createdAt"
     FROM applications a JOIN jobs j ON j.id = a.job_id
     LEFT JOIN companies c ON c.slug = j.company_slug
     WHERE a.user_id = $1 ORDER BY a.created_at DESC`,
    [userId],
  );
  return rows;
}
