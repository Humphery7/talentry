import { pool } from '../db/pool.js';
import { getCareer, postCareer } from './career.service.js';

const MISSING_TABLE = '42P01';

export interface Recommendation {
  jobId: number;
  rank: number;
  score: number;
  similarity: number | null;
  reason: string | null;
  title: string;
  url: string;
  locations: string[];
  employmentType: string | null;
  workplaceType: string | null;
  seniority: string | null;
  occupation: string | null;
  company: string | null;
}

export interface RecommendationMeta {
  /** When the current list was generated, or null if there is none yet. */
  generatedAt: string | null;
  /** True when the profile embedding changed after the list was generated. */
  profileChanged: boolean;
  /** Open, embeddable jobs that appeared or were embedded after generation. */
  newJobs: number;
}

export interface Recommendations {
  data: Recommendation[];
  meta: RecommendationMeta;
}

interface MetaRow {
  generatedAt: Date | null;
  embeddingUpdatedAt: Date | null;
  newJobs: number | null;
}

const META_SQL = `
  SELECT
    (SELECT max(created_at) FROM job_recommendations WHERE user_id = $1)
      AS "generatedAt",
    (SELECT embedding_updated_at FROM candidate_profiles WHERE user_id = $1)
      AS "embeddingUpdatedAt",
    (SELECT count(*)::int
       FROM jobs
      WHERE status = 'open'
        AND embedding IS NOT NULL
        AND (
          first_seen_at::timestamptz >
            (SELECT max(created_at) FROM job_recommendations WHERE user_id = $1)
          OR embedding_updated_at >
            (SELECT max(created_at) FROM job_recommendations WHERE user_id = $1)
        )
    ) AS "newJobs"
`;

function emptyMeta(): RecommendationMeta {
  return { generatedAt: null, profileChanged: false, newJobs: 0 };
}

function isMissingTable(err: unknown): boolean {
  return (err as { code?: string }).code === MISSING_TABLE;
}

async function getMeta(userId: string): Promise<RecommendationMeta> {
  try {
    const { rows } = await pool.query<MetaRow>(META_SQL, [userId]);
    const row = rows[0];
    if (!row?.generatedAt) return emptyMeta();

    return {
      generatedAt: row.generatedAt.toISOString(),
      profileChanged:
        row.embeddingUpdatedAt !== null &&
        row.embeddingUpdatedAt > row.generatedAt,
      newJobs: row.newJobs ?? 0,
    };
  } catch (err) {
    // The career service owns this table; before its first run it may not exist.
    if (isMissingTable(err)) return emptyMeta();
    throw err;
  }
}

async function load(userId: string): Promise<Recommendations> {
  const data = await getCareer<Recommendation[]>(
    `/recommendations/${userId}`,
  );
  return { data, meta: await getMeta(userId) };
}

/** Reads the user's saved recommendations plus whether they are out of date. */
export function get(userId: string): Promise<Recommendations> {
  return load(userId);
}

/** Regenerates the user's recommendations, then returns the new list. */
export async function refresh(userId: string): Promise<Recommendations> {
  await postCareer<{ count: number }>(`/recommendations/${userId}`, {});
  return load(userId);
}
