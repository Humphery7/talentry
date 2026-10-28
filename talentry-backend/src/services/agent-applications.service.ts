import type { PoolClient } from 'pg';
import { pool } from '../db/pool.js';
import { HttpError } from '../utils/http-error.js';
import { getCareer, postCareer } from './career.service.js';

export interface AgentApplicationItem {
  jobId: number;
  status: string;
}

export interface AgentApplicationBatch {
  batchId: string;
  count: number;
  jobs: AgentApplicationItem[];
}

interface CareerAttention {
  id: string;
  kind: 'question' | 'manual';
  question: string;
  answer: string | null;
}

interface CareerPlanField {
  label: string;
  kind: string;
  required: boolean;
  value: string;
  source: string;
  status: string;
  options?: string[] | null;
  doc?: string | null;
  pos?: number;
  sensitive?: boolean;
  note?: string | null;
}

interface CareerPlan {
  fields?: Record<string, CareerPlanField>;
}

interface CareerDocument {
  kind: string;
  version: number;
  origin: string;
  notes: string[];
  content: string;
}

interface CareerSummary {
  id: string;
  batchId: string;
  jobId: number;
  status: string;
  platform: string | null;
  applyUrl: string | null;
  jobTitle: string | null;
  company: string | null;
  error: string | null;
  warningCount: number;
  attentionCount: number;
  createdAt: string;
  updatedAt: string;
  approvedAt: string | null;
  submittedAt: string | null;
  screenshot?: string | null;
}

interface CareerDetail extends CareerSummary {
  plan: CareerPlan;
  attention: CareerAttention[];
  warnings: string[];
  options: Record<string, unknown>;
  documents: CareerDocument[];
  result: Record<string, unknown> | null;
}

interface ApplicationRow {
  id: string;
  status: string;
  plan: CareerPlan;
  attention: CareerAttention[];
  options: Record<string, unknown>;
}

interface DocumentGroup extends CareerDocument {
  versions: { version: number; origin: string }[];
}

const MISSING_TABLE = '42P01';
const EDITABLE = ['needs_input', 'pending_approval', 'approved'];
const PAUSED = ['needs_input', 'pending_approval'];

function isMissingTable(err: unknown): boolean {
  return (err as { code?: string }).code === MISSING_TABLE;
}

function normalize(text: string): string {
  return text
    .toLowerCase()
    .replace(/[*✱]/g, ' ')
    .replace(/[^\p{L}\p{N}_\s]/gu, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function careerPath(path: string, userId: string): string {
  const join = path.includes('?') ? '&' : '?';
  return `${path}${join}user_id=${encodeURIComponent(userId)}`;
}

function groupDocuments(documents: CareerDocument[]) {
  const grouped: Record<string, DocumentGroup> = {};
  for (const document of documents) {
    const current = grouped[document.kind];
    if (!current) {
      grouped[document.kind] = {
        ...document,
        versions: [{ version: document.version, origin: document.origin }],
      };
    } else {
      current.versions.push({
        version: document.version,
        origin: document.origin,
      });
    }
  }
  return grouped;
}

async function eventsFor(id: string) {
  try {
    const { rows } = await pool.query(
      `SELECT kind, message, created_at AS "createdAt"
       FROM agent_application_events
       WHERE agent_application_id = $1
       ORDER BY id DESC
       LIMIT 60`,
      [id],
    );
    return rows;
  } catch (err) {
    if (isMissingTable(err)) return [];
    throw err;
  }
}

async function event(
  db: { query: PoolClient['query'] },
  id: string,
  kind: string,
  message: string,
) {
  await db.query(
    `INSERT INTO agent_application_events (agent_application_id, kind, message)
     VALUES ($1, $2, $3)`,
    [id, kind, message],
  );
}

async function withApplication<T>(
  userId: string,
  id: string,
  fn: (client: PoolClient, row: ApplicationRow) => Promise<T>,
): Promise<T> {
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const { rows } = await client.query<ApplicationRow>(
      `SELECT id, status, plan, attention, options
       FROM agent_applications
       WHERE id = $1 AND user_id = $2
       FOR UPDATE`,
      [id, userId],
    );
    if (!rows[0]) throw new HttpError(404, 'Application not found.');
    const result = await fn(client, rows[0]);
    await client.query('COMMIT');
    return result;
  } catch (err) {
    await client.query('ROLLBACK').catch(() => undefined);
    if (isMissingTable(err)) {
      throw new HttpError(404, 'Application not found.');
    }
    throw err;
  } finally {
    client.release();
  }
}

async function voidApproval(
  db: PoolClient,
  app: ApplicationRow,
): Promise<void> {
  if (app.status === 'in_progress' || app.status === 'submitting') {
    throw new HttpError(
      409,
      'Submission is in progress; it can no longer be edited.',
    );
  }
  if (!EDITABLE.includes(app.status)) {
    throw new HttpError(409, 'This application cannot be edited now.');
  }
  const status = app.status === 'approved' ? 'pending_approval' : app.status;
  await db.query(
    `UPDATE agent_applications
     SET approved_snapshot = NULL,
         approved_at = NULL,
         status = $2,
         updated_at = now()
     WHERE id = $1`,
    [app.id, status],
  );
  app.status = status;
}

export function start(
  userId: string,
  jobIds: number[],
): Promise<AgentApplicationBatch> {
  return postCareer<AgentApplicationBatch>('/agent-applications', {
    user_id: userId,
    job_ids: jobIds,
  });
}

/** Queue the best recommended jobs that have no application for this user. */
export async function queueTop(
  userId: string,
  limit: number,
): Promise<{ queued: number }> {
  const { rows } = await pool.query<{ jobId: string }>(
    `SELECT r.job_id AS "jobId"
     FROM job_recommendations r
     JOIN jobs j ON j.id = r.job_id
     WHERE r.user_id = $1
       AND j.status = 'open'
       AND NOT EXISTS (
         SELECT 1 FROM agent_applications a
         WHERE a.user_id = r.user_id AND a.job_id = r.job_id
       )
     ORDER BY r.rank
     LIMIT $2`,
    [userId, limit],
  );
  const jobIds = rows
    .map((row) => Number(row.jobId))
    .filter((jobId) => Number.isInteger(jobId));
  if (!jobIds.length) return { queued: 0 };
  const batch = await start(userId, jobIds);
  return { queued: batch.count };
}

export async function list(userId: string) {
  try {
    const { rows } = await pool.query(
      `SELECT a.id,
              a.batch_id AS "batchId",
              a.job_id AS "jobId",
              a.status,
              a.platform,
              a.apply_url AS "applyUrl",
              j.title AS "jobTitle",
              c.name AS company,
              a.error,
              COALESCE(jsonb_array_length(a.warnings), 0) AS "warningCount",
              (
                SELECT count(*)::int
                FROM jsonb_array_elements(a.attention) item
                WHERE item ->> 'answer' IS NULL
              ) AS "attentionCount",
              a.created_at AS "createdAt",
              a.updated_at AS "updatedAt",
              a.approved_at AS "approvedAt",
              a.submitted_at AS "submittedAt"
       FROM agent_applications a
       JOIN jobs j ON j.id = a.job_id
       LEFT JOIN companies c ON c.slug = j.company_slug
       WHERE a.user_id = $1
       ORDER BY a.created_at DESC
       LIMIT 50`,
      [userId],
    );
    return rows.map((row) => ({ ...row, jobId: Number(row.jobId) }));
  } catch (err) {
    if (isMissingTable(err)) return [];
    throw err;
  }
}

export async function get(userId: string, id: string) {
  const detail = await getCareer<CareerDetail>(
    careerPath(`/agent-applications/${id}`, userId),
  );
  const fields = Object.entries(detail.plan?.fields ?? {})
    .map(([key, field]) => ({ key, ...field }))
    .sort((left, right) => (left.pos ?? 0) - (right.pos ?? 0));

  return {
    ...detail,
    fields,
    documents: groupDocuments(detail.documents ?? []),
    events: await eventsFor(id),
  };
}

export async function answer(
  userId: string,
  id: string,
  answers: { id: string; answer: string }[],
) {
  const record = Object.fromEntries(
    answers.map((item) => [item.id, item.answer]),
  );
  return postCareer<{ id: string; status: string; answered: number }>(
    careerPath(`/agent-applications/${id}/answers`, userId),
    { answers: record },
  );
}

export function approve(userId: string, id: string) {
  return postCareer<CareerDetail>(
    careerPath(`/agent-applications/${id}/approve`, userId),
    {},
  );
}

export async function retry(
  userId: string,
  id: string,
  confirmNotSubmitted: boolean,
) {
  if (!confirmNotSubmitted) {
    const current = await getCareer<CareerSummary>(
      careerPath(`/agent-applications/${id}`, userId),
    );
    if (current.status === 'unconfirmed') {
      throw new HttpError(
        409,
        'We could not confirm whether this was submitted. Check your email or the employer site, then confirm you have not already applied.',
      );
    }
  }
  return postCareer<CareerDetail>(
    careerPath(`/agent-applications/${id}/retry`, userId),
    {},
  );
}

export function cancel(userId: string, id: string) {
  return postCareer<CareerDetail>(
    careerPath(`/agent-applications/${id}/cancel`, userId),
    {},
  );
}

/** The user did the manual step: re-run from the saved plan. */
export function resume(userId: string, id: string) {
  return withApplication(userId, id, async (db, app) => {
    if (app.status !== 'needs_input') {
      throw new HttpError(409, 'Nothing to resume.');
    }
    const attention = app.attention ?? [];
    if (
      attention.some((item) => item.kind === 'question' && item.answer == null)
    ) {
      throw new HttpError(409, 'Answer the open questions first.');
    }
    const remaining = attention.filter((item) => item.kind !== 'manual');
    await db.query(
      `UPDATE agent_applications
       SET attention = $2,
           status = 'queued',
           approved_snapshot = NULL,
           approved_at = NULL,
           error = NULL,
           run_after = now(),
           updated_at = now()
       WHERE id = $1`,
      [id, JSON.stringify(remaining)],
    );
    await event(db, id, 'resumed', 'Resuming from where it stopped.');
    return { status: 'queued' };
  });
}

/** The user submitted on the employer site instead. */
export function markSubmittedManually(userId: string, id: string) {
  return withApplication(userId, id, async (db, app) => {
    if (
      !['needs_input', 'pending_approval', 'unconfirmed', 'failed'].includes(
        app.status,
      )
    ) {
      throw new HttpError(
        409,
        'This application cannot be marked as submitted now.',
      );
    }
    await db.query(
      `UPDATE agent_applications
       SET status = 'submitted',
           submitted_at = now(),
           completed_at = now(),
           result = $2,
           error = NULL,
           approved_snapshot = NULL,
           approved_at = NULL,
           updated_at = now()
       WHERE id = $1`,
      [id, JSON.stringify({ manual: true })],
    );
    await event(db, id, 'submitted', 'You marked this as submitted yourself.');
    return { status: 'submitted' };
  });
}

export function editField(
  userId: string,
  id: string,
  key: string,
  value: string,
) {
  return withApplication(userId, id, async (db, app) => {
    const plan = app.plan ?? {};
    const field = plan.fields?.[key];
    if (!field) throw new HttpError(404, 'No such field.');
    if (field.kind === 'file') {
      throw new HttpError(
        400,
        'Documents are edited in the documents section.',
      );
    }
    await voidApproval(db, app);

    let next = value.trim();
    if (field.options?.length && next) {
      const hit = field.options.find(
        (option) => normalize(option) === normalize(next),
      );
      if (!hit) {
        throw new HttpError(400, `Choose one of: ${field.options.join(', ')}.`);
      }
      next = hit;
    }
    if (!next && field.required) {
      throw new HttpError(400, 'This field is required.');
    }

    field.value = next;
    field.source = 'user_edit';
    field.status = next ? 'user' : 'skipped';
    await db.query(
      'UPDATE agent_applications SET plan = $2, updated_at = now() WHERE id = $1',
      [id, JSON.stringify(plan)],
    );
    await event(db, id, 'edited', `Edited “${field.label}”.`);
    return { ok: true };
  });
}

export function saveDocument(
  userId: string,
  id: string,
  kind: 'cv' | 'cover_letter',
  content: string,
) {
  return withApplication(userId, id, async (db, app) => {
    await voidApproval(db, app);
    const { rows } = await db.query<{ version: number }>(
      `INSERT INTO agent_application_documents
         (agent_application_id, kind, version, content, origin)
       VALUES (
         $1,
         $2,
         (
           SELECT COALESCE(MAX(version), 0) + 1
           FROM agent_application_documents
           WHERE agent_application_id = $1 AND kind = $2
         ),
         $3,
         'user_edit'
       )
       RETURNING version`,
      [id, kind, content],
    );
    const version = rows[0].version;

    const plan = app.plan ?? {};
    for (const field of Object.values(plan.fields ?? {})) {
      if (field.doc !== kind) continue;
      field.value =
        field.kind === 'textarea'
          ? content.trim()
          : `${kind.replace('_', ' ')} v${version}`;
      field.source = 'user_edit';
      field.status = field.kind === 'textarea' ? 'draft' : 'document';
    }
    await db.query(
      'UPDATE agent_applications SET plan = $2, updated_at = now() WHERE id = $1',
      [id, JSON.stringify(plan)],
    );
    await event(
      db,
      id,
      'document',
      `Saved your edited ${kind === 'cv' ? 'CV' : 'cover letter'} (v${version}).`,
    );
    return { version };
  });
}

export function regenerate(
  userId: string,
  id: string,
  kind: 'cv' | 'cover_letter',
) {
  return withApplication(userId, id, async (db, app) => {
    if (!PAUSED.includes(app.status) && app.status !== 'approved') {
      throw new HttpError(409, 'Cannot regenerate now.');
    }
    const options: Record<string, unknown> = {
      ...app.options,
      regenerate: [kind],
    };
    if (kind === 'cover_letter') options.coverLetter = true;
    await db.query(
      `UPDATE agent_applications
       SET options = $2,
           status = 'queued',
           approved_snapshot = NULL,
           approved_at = NULL,
           error = NULL,
           run_after = now(),
           updated_at = now()
       WHERE id = $1`,
      [id, JSON.stringify(options)],
    );
    await event(
      db,
      id,
      'regenerate',
      `Regenerating the ${kind === 'cv' ? 'CV' : 'cover letter'}.`,
    );
    return { status: 'queued' };
  });
}
