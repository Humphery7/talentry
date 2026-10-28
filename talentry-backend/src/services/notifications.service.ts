import { pool } from '../db/pool.js';

const MISSING_TABLE = '42P01';

export interface NotificationItem {
  id: string;
  applicationId: string | null;
  kind: string;
  title: string;
  body: string;
  readAt: string | null;
  createdAt: string;
}

function isMissingTable(err: unknown): boolean {
  return (err as { code?: string }).code === MISSING_TABLE;
}

export async function list(userId: string) {
  try {
    const { rows } = await pool.query<NotificationItem>(
      `SELECT id,
              agent_application_id AS "applicationId",
              kind,
              title,
              body,
              read_at AS "readAt",
              created_at AS "createdAt"
       FROM notifications
       WHERE user_id = $1
       ORDER BY created_at DESC
       LIMIT 30`,
      [userId],
    );
    const unread = await pool.query<{ n: number }>(
      `SELECT count(*)::int AS n
       FROM notifications
       WHERE user_id = $1 AND read_at IS NULL`,
      [userId],
    );
    return { unread: unread.rows[0]?.n ?? 0, items: rows };
  } catch (err) {
    // The career service owns this table; it may not exist before its first run.
    if (isMissingTable(err)) return { unread: 0, items: [] };
    throw err;
  }
}

export async function markRead(userId: string, ids: string[] | 'all') {
  try {
    if (ids === 'all') {
      await pool.query(
        `UPDATE notifications
         SET read_at = now()
         WHERE user_id = $1 AND read_at IS NULL`,
        [userId],
      );
    } else {
      await pool.query(
        `UPDATE notifications
         SET read_at = now()
         WHERE user_id = $1 AND id = ANY($2::uuid[]) AND read_at IS NULL`,
        [userId, ids],
      );
    }
    return { ok: true };
  } catch (err) {
    if (isMissingTable(err)) return { ok: true };
    throw err;
  }
}
