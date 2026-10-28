import { pool } from '../db/pool.js';
import { HttpError } from '../utils/http-error.js';
import type { InterviewAnswer } from '../validators/interview.validator.js';
import { postCareer } from './career.service.js';

const MISSING_TABLE = '42P01';

export interface SectionProgress {
  id: string;
  completedItems: number;
  totalItems: number;
  percent: number;
}

export interface InterviewProgress {
  totalItems: number;
  completedItems: number;
  percent: number;
  readiness: number | null;
  sections: SectionProgress[];
}

export interface PublicOption {
  id: string;
  text: string;
}

export interface PublicResource {
  provider: string;
  title: string;
  url: string;
}

export interface PublicItem {
  id: string;
  type: string;
  question: string;
  instructions: string | null;
  topic: string;
  difficulty: string;
  relevance: string;
  estimatedMinutes: number;
  options?: PublicOption[];
  resource?: PublicResource;
  completed?: boolean;
  response?: {
    answer: Record<string, unknown> | null;
    score: number | null;
    feedback: Record<string, unknown> | null;
  } | null;
  progress?: SectionProgress;
}

export interface PublicSection {
  id: string;
  type: string;
  title: string;
  priority: string;
  description: string;
  estimatedMinutes: number;
  items: PublicItem[];
  progress?: SectionProgress;
}

export interface PublicAssessment {
  title: string;
  roleFamily: string;
  summary: string;
  estimatedMinutes: number;
  sections: PublicSection[];
}

export interface InterviewAttempt {
  id: string;
  jobId: number;
  attemptNo: number;
  status: string;
  title: string;
  roleFamily: string;
  progress: InterviewProgress;
  createdAt: string;
  updatedAt: string;
  completedAt: string | null;
  assessment: PublicAssessment;
}

export interface InterviewSummary {
  id: string;
  jobId: number;
  attemptNo: number;
  status: string;
  title: string;
  roleFamily: string;
  progress: InterviewProgress;
  createdAt: string;
  updatedAt: string;
  completedAt: string | null;
}

interface CareerGenerateResult {
  attempt_id: string;
  created: boolean;
}

interface CareerAnswerResult {
  itemId: string;
  score: number | null;
  feedback: Record<string, unknown>;
  completed: boolean;
  progress: InterviewProgress;
}

interface ResponseRow {
  itemId: string;
  answer: Record<string, unknown> | null;
  score: number | null;
  feedback: Record<string, unknown> | null;
  completed: boolean;
}

function isMissingTable(err: unknown): boolean {
  return (err as { code?: string }).code === MISSING_TABLE;
}

function attemptSql(where: string) {
  return `
    SELECT id, job_id AS "jobId", attempt_no AS "attemptNo", status, title,
           role_family AS "roleFamily", progress, created_at AS "createdAt",
           updated_at AS "updatedAt", completed_at AS "completedAt",
           assessment_public AS assessment
    FROM interview_attempts
    ${where}
  `;
}

async function loadAttemptRow(
  attemptId: string,
  userId: string,
): Promise<(InterviewSummary & { assessment: PublicAssessment }) | null> {
  try {
    const { rows } = await pool.query(
      attemptSql('WHERE id = $1 AND user_id = $2'),
      [attemptId, userId],
    );
    return rows[0] ?? null;
  } catch (err) {
    // The career service owns these tables; before its first run they may not exist.
    if (isMissingTable(err)) return null;
    throw err;
  }
}

export async function startAttempt(
  userId: string,
  jobId: number,
  newAttempt: boolean,
): Promise<InterviewAttempt> {
  const job = await pool.query('SELECT id FROM jobs WHERE id = $1', [jobId]);
  if (!job.rowCount) throw new HttpError(404, 'Job not found.');

  const result = await postCareer<CareerGenerateResult>('/interview/generate', {
    user_id: userId,
    job_id: jobId,
    new_attempt: newAttempt,
  });

  const attempt = await getAttempt(userId, result.attempt_id);
  return attempt;
}

export async function listAttempts(
  userId: string,
  jobId?: number,
): Promise<{ data: InterviewSummary[] }> {
  try {
    const { rows } = await pool.query(
      `
      SELECT id, job_id AS "jobId", attempt_no AS "attemptNo", status, title,
             role_family AS "roleFamily", progress, created_at AS "createdAt",
             updated_at AS "updatedAt", completed_at AS "completedAt"
      FROM interview_attempts
      WHERE user_id = $1 AND ($2::bigint IS NULL OR job_id = $2)
      ORDER BY attempt_no DESC
      `,
      [userId, jobId ?? null],
    );
    return { data: rows as InterviewSummary[] };
  } catch (err) {
    if (isMissingTable(err)) return { data: [] };
    throw err;
  }
}

export async function getAttempt(
  userId: string,
  attemptId: string,
): Promise<InterviewAttempt> {
  const row = await loadAttemptRow(attemptId, userId);
  if (!row) throw new HttpError(404, 'Interview attempt not found.');

  const { rows } = await pool.query<ResponseRow>(
    `
    SELECT item_id AS "itemId", answer, score, feedback, completed
    FROM interview_responses
    WHERE attempt_id = $1
    `,
    [attemptId],
  );
  const byItem = new Map(rows.map((response) => [response.itemId, response]));
  const progress = row.progress as InterviewProgress;
  const assessment = row.assessment;

  const sections: PublicSection[] = assessment.sections.map((section) => ({
    ...section,
    progress: progress.sections.find((item) => item.id === section.id),
    items: section.items.map((item) => {
      const response = byItem.get(item.id);
      return {
        ...item,
        completed: response?.completed ?? false,
        response: response
          ? {
              answer: response.answer,
              score: response.score,
              feedback: response.feedback,
            }
          : null,
      };
    }),
  }));

  return {
    id: row.id,
    jobId: Number(row.jobId),
    attemptNo: row.attemptNo,
    status: row.status,
    title: row.title,
    roleFamily: row.roleFamily,
    progress,
    createdAt: row.createdAt,
    updatedAt: row.updatedAt,
    completedAt: row.completedAt,
    assessment: { ...assessment, sections },
  };
}

export async function submitResponse(
  userId: string,
  attemptId: string,
  itemId: string,
  answer: InterviewAnswer,
): Promise<CareerAnswerResult> {
  let owned;
  try {
    owned = await pool.query(
      'SELECT id FROM interview_attempts WHERE id = $1 AND user_id = $2',
      [attemptId, userId],
    );
  } catch (err) {
    if (isMissingTable(err)) {
      throw new HttpError(404, 'Interview attempt not found.');
    }
    throw err;
  }
  if (!owned.rowCount) throw new HttpError(404, 'Interview attempt not found.');

  return postCareer<CareerAnswerResult>('/interview/evaluate', {
    user_id: userId,
    attempt_id: attemptId,
    item_id: itemId,
    answer,
  });
}

export async function getFeedback(userId: string, attemptId: string) {
  const row = await loadAttemptRow(attemptId, userId);
  if (!row) throw new HttpError(404, 'Interview attempt not found.');

  const { rows } = await pool.query<ResponseRow>(
    `
    SELECT item_id AS "itemId", answer, score, feedback, completed
    FROM interview_responses
    WHERE attempt_id = $1
    `,
    [attemptId],
  );

  const metadata = new Map<
    string,
    { question: string; topic: string; type: string; order: number }
  >();
  let order = 0;
  for (const section of row.assessment.sections) {
    for (const item of section.items) {
      metadata.set(item.id, {
        question: item.question,
        topic: item.topic,
        type: item.type,
        order: order++,
      });
    }
  }

  const items = rows
    .map((response) => ({
      itemId: response.itemId,
      ...metadata.get(response.itemId),
      score: response.score,
      feedback: response.feedback,
      completed: response.completed,
    }))
    .sort((a, b) => (a.order ?? 0) - (b.order ?? 0));

  return { progress: row.progress, items };
}
