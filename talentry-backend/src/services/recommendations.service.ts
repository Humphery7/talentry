import { pool } from '../db/pool.js';
import type { JobsQuery } from '../validators/jobs.validator.js';
import { getCareer, postCareer } from './career.service.js';
import { buildWhere, getLocationIndex } from './jobs.service.js';

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

/**
 * The saved career-coach scope. Same keys as the jobs page URL, minus salary:
 * salary does not help semantic matching and the crawl has almost no data.
 * Values are region slugs for `loc` (e.g. `us`), labels for `lvl`, and slugs
 * for `sch` / `types`.
 */
export interface RecommendationFilters {
  loc?: string[];
  lvl?: string[];
  ind?: string[];
  sch?: string[];
  types?: string[];
  roles?: string[];
  q?: string;
}

export interface RecommendationMeta {
  /** When the current list was generated, or null if there is none yet. */
  generatedAt: string | null;
  /** True when the profile embedding changed after the list was generated. */
  profileChanged: boolean;
  /** Open, embeddable jobs inside the saved scope that appeared afterwards. */
  newJobs: number;
}

export interface Recommendations {
  data: Recommendation[];
  meta: RecommendationMeta;
  /** The scope the current list was built with; `{}` means no filters. */
  filters: RecommendationFilters;
}

interface MetaRow {
  generatedAt: Date | null;
  embeddingUpdatedAt: Date | null;
}

const LIST_KEYS = ['loc', 'lvl', 'ind', 'sch', 'types', 'roles'] as const;

const META_SQL = `
  SELECT
    (SELECT max(created_at) FROM job_recommendations WHERE user_id = $1)
      AS "generatedAt",
    (SELECT embedding_updated_at FROM candidate_profiles WHERE user_id = $1)
      AS "embeddingUpdatedAt"
`;

const FILTERS_SQL = `
  SELECT filters FROM recommendation_filters WHERE user_id = $1
`;

function emptyMeta(): RecommendationMeta {
  return { generatedAt: null, profileChanged: false, newJobs: 0 };
}

function isMissingTable(err: unknown): boolean {
  return (err as { code?: string }).code === MISSING_TABLE;
}

/**
 * Keep only known keys and turn everything into short, deduplicated strings.
 * Input may come from the browser, so it must not be trusted.
 */
export function normalizeFilters(raw: unknown): RecommendationFilters {
  const out: RecommendationFilters = {};
  if (!raw || typeof raw !== 'object') return out;
  const source = raw as Record<string, unknown>;

  for (const key of LIST_KEYS) {
    const value = source[key];
    const list = Array.isArray(value)
      ? value
      : typeof value === 'string'
        ? value.split(',')
        : [];
    const items = [
      ...new Set(
        list
          .map((item) => String(item).trim().slice(0, 80))
          .filter(Boolean),
      ),
    ].slice(0, 20);
    if (items.length) out[key] = items;
  }

  const keywords = source.q;
  if (typeof keywords === 'string' && keywords.trim()) {
    out.q = keywords.trim().slice(0, 120);
  }

  return out;
}

async function getFilters(userId: string): Promise<RecommendationFilters> {
  try {
    const { rows } = await pool.query<{ filters: unknown }>(FILTERS_SQL, [
      userId,
    ]);
    return normalizeFilters(rows[0]?.filters);
  } catch (err) {
    // talentry-career owns this table; before its first run it may not exist.
    if (isMissingTable(err)) return {};
    throw err;
  }
}

function toJobsQuery(filters: RecommendationFilters): JobsQuery {
  return {
    status: 'open',
    ...(filters.q ? { q: filters.q } : {}),
    ...(filters.loc?.length ? { loc: filters.loc.join(',') } : {}),
    ...(filters.lvl?.length ? { lvl: filters.lvl.join(',') } : {}),
    ...(filters.ind?.length ? { ind: filters.ind.join(',') } : {}),
    ...(filters.sch?.length ? { sch: filters.sch.join(',') } : {}),
    ...(filters.types?.length ? { types: filters.types.join(',') } : {}),
    ...(filters.roles?.length ? { roles: filters.roles.join(',') } : {}),
  };
}

/** "New jobs" means new *and eligible*; otherwise the banner nags forever. */
async function countNewJobs(
  since: Date,
  filters: RecommendationFilters,
): Promise<number> {
  const regionLocs = filters.loc?.length
    ? await getLocationIndex().catch(() => undefined)
    : undefined;
  const { sql, params } = buildWhere(toJobsQuery(filters), regionLocs);
  const sinceParam = `$${params.length + 1}`;
  const extra = [
    'j.embedding IS NOT NULL',
    `(j.first_seen_at::timestamptz > ${sinceParam} OR j.embedding_updated_at > ${sinceParam})`,
  ].join(' AND ');

  const { rows } = await pool.query<{ count: number }>(
    `SELECT count(*)::int AS count
       FROM jobs j
       LEFT JOIN companies c ON c.slug = j.company_slug
       ${sql ? `${sql} AND ` : 'WHERE '}${extra}`,
    [...params, since],
  );
  return rows[0]?.count ?? 0;
}

async function getMeta(
  userId: string,
  filters: RecommendationFilters,
): Promise<RecommendationMeta> {
  try {
    const { rows } = await pool.query<MetaRow>(META_SQL, [userId]);
    const row = rows[0];
    if (!row?.generatedAt) return emptyMeta();

    return {
      generatedAt: row.generatedAt.toISOString(),
      profileChanged:
        row.embeddingUpdatedAt !== null &&
        row.embeddingUpdatedAt > row.generatedAt,
      newJobs: await countNewJobs(row.generatedAt, filters),
    };
  } catch (err) {
    // The career service owns this table; before its first run it may not exist.
    if (isMissingTable(err)) return emptyMeta();
    throw err;
  }
}

async function load(userId: string): Promise<Recommendations> {
  const filters = await getFilters(userId);
  const [data, meta] = await Promise.all([
    getCareer<Recommendation[]>(`/recommendations/${userId}`),
    getMeta(userId, filters),
  ]);
  return { data, meta, filters };
}

/** Reads the user's saved recommendations plus whether they are out of date. */
export function get(userId: string): Promise<Recommendations> {
  return load(userId);
}

/**
 * Regenerates the user's recommendations, then returns the new list.
 *
 * `filters === undefined` means "keep the saved scope". Passing an object
 * replaces it, and `{}` clears it, so the coach page can remove all filters.
 */
export async function refresh(
  userId: string,
  filters?: unknown,
): Promise<Recommendations> {
  const next = filters === undefined ? undefined : normalizeFilters(filters);
  await postCareer(
    `/recommendations/${userId}`,
    next === undefined ? {} : { filters: next },
  );
  return load(userId);
}
