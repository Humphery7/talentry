import { pool } from '../db/pool.js';
import { HttpError } from '../utils/http-error.js';
import type { JobsQuery } from '../validators/jobs.validator.js';

const SELECT = `
  SELECT j.id, j.url, j.company_slug AS "companySlug", j.board_slug AS "boardSlug",
    j.monitor_type AS "monitorType", j.title, j.description,
    j.locations_json AS "locationsJson", j.employment_type AS "employmentType",
    j.workplace_type AS "workplaceType", j.date_posted AS "datePosted",
    j.salary_json AS "salaryJson", j.metadata_json AS "metadataJson",
    j.seniority, j.occupation, j.technologies_json AS "technologiesJson",
    j.status, j.first_seen_at AS "firstSeenAt", j.last_seen_at AS "lastSeenAt",
    j.closed_at AS "closedAt",
    c.name AS "companyName", c.website AS "companyWebsite",
    c.logo_url AS "companyLogo", c.icon_url AS "companyIcon",
    c.industry AS "companyIndustry",
    c.employee_count_range AS "companySize", c.founded_year AS "companyFounded"
  FROM jobs j LEFT JOIN companies c ON c.slug = j.company_slug
`;

/** UI experience labels -> seniority values stored by the crawler. */
const LEVEL_MAP: Record<string, string[]> = {
  'junior level': ['entry', 'junior'],
  'mid level': ['mid'],
  'senior level': ['senior', 'staff', 'principal', 'director', 'lead'],
};

/** First present key among salary_json variants, as a number (or NULL). */
const salaryExpr = (...keys: string[]) =>
  `COALESCE(${keys.map((k) => `((j.salary_json)::jsonb ->> '${k}')`).join(', ')})::numeric`;
const SAL_MIN = salaryExpr(
  'min',
  'salary_min',
  'min_salary',
  'low',
  'amount',
  'value',
);
const SAL_MAX = salaryExpr(
  'max',
  'salary_max',
  'max_salary',
  'high',
  'amount',
  'value',
);

/** 'Full time' and 'FullTime' should match the same rows. */
const normType = (t: string) => t.toLowerCase().replace(/[\s_-]+/g, '');

function parseJsonArray(raw: unknown): string[] {
  if (!raw) return [];
  try {
    const v: unknown = typeof raw === 'string' ? JSON.parse(raw) : raw;
    return Array.isArray(v) ? v.map(String) : [];
  } catch {
    return [];
  }
}

function parseJson(raw: unknown): unknown {
  if (!raw) return null;
  try {
    return typeof raw === 'string' ? JSON.parse(raw) : raw;
  } catch {
    return null;
  }
}

/** Builds WHERE + params. Shared by the page query and the count query. */
function buildWhere(q: JobsQuery): { sql: string; params: unknown[] } {
  const conds: string[] = [];
  const params: unknown[] = [];
  // Postgres placeholders are 1-based ($1, $2, ...): each push mints the next one.
  const p = (value: unknown) => `$${params.push(value)}`;

  const status = q.status ?? 'open';
  if (status !== 'all') conds.push(`j.status = ${p(status)}`);

  if (q.q?.trim()) {
    const like = `%${q.q.trim()}%`;
    conds.push(`(j.title ILIKE ${p(like)} OR c.name ILIKE ${p(like)})`);
  }
  if (q.co?.trim()) {
    conds.push(
      `(c.slug = ${p(q.co.trim())} OR c.name ILIKE ${p(`%${q.co.trim()}%`)})`,
    );
  }
  if (q.ind?.trim()) conds.push(`c.industry ILIKE ${p(`%${q.ind.trim()}%`)}`);
  if (q.loc?.trim()) {
    conds.push(
      `j.locations_json IS NOT NULL AND EXISTS (
         SELECT 1 FROM jsonb_array_elements_text((j.locations_json)::jsonb) AS loc
         WHERE loc ILIKE ${p(`%${q.loc.trim()}%`)}
       )`,
    );
  }
  if (q.lvl?.trim()) {
    const levels = LEVEL_MAP[q.lvl.trim().toLowerCase()] ?? [
      q.lvl.trim().toLowerCase(),
    ];
    conds.push(`lower(j.seniority) = ANY(${p(levels)})`);
  }
  if (q.roles?.trim()) {
    const roles = q.roles
      .split(',')
      .map((r) => r.trim().toLowerCase())
      .filter(Boolean);
    if (roles.length) conds.push(`lower(j.occupation) = ANY(${p(roles)})`);
  }
  const typeList = [
    ...(q.typ?.trim() ? [q.typ.trim()] : []),
    ...(q.types
      ? q.types
          .split(',')
          .map((t) => t.trim())
          .filter(Boolean)
      : []),
  ];
  if (typeList.length) {
    conds.push(
      `replace(lower(COALESCE(j.employment_type, '')), ' ', '') = ANY(${p(typeList.map(normType))})`,
    );
  }
  if (q.sch?.trim()) {
    const like = `%${q.sch.trim()}%`;
    conds.push(
      `(j.workplace_type ILIKE ${p(like)} OR j.employment_type ILIKE ${p(like)} OR j.description ILIKE ${p(like)})`,
    );
  }
  // Salary data is sparse (all NULL in the current crawl): NULL salaries pass
  // the range instead of vanishing. Extracts {min,max}-style JSON when present.
  // The UI sends thousands ($35K), while the crawler stores yearly dollars.
  if (q.lo !== undefined || q.hi !== undefined) {
    const min = (q.lo ?? 0) * 1000;
    const max = (q.hi ?? 999_999) * 1000;
    conds.push(
      `(j.salary_json IS NULL OR ${SAL_MIN} IS NULL OR ${SAL_MIN} <= ${p(max)})`,
    );
    conds.push(
      `(j.salary_json IS NULL OR ${SAL_MAX} IS NULL OR ${SAL_MAX} >= ${p(min)})`,
    );
  }
  if (q.ids?.trim()) {
    const ids = q.ids
      .split(',')
      .map(Number)
      .filter((n) => Number.isInteger(n));
    conds.push(ids.length ? `j.id = ANY(${p(ids)})` : `FALSE`);
  }
  return { sql: conds.length ? `WHERE ${conds.join(' AND ')}` : '', params };
}

/** Turns a raw database row into the JSON shape the frontend consumes. */
function mapRow(r: Record<string, unknown>) {
  return {
    id: Number(r.id),
    url: r.url,
    title: r.title,
    description: r.description,
    locations: parseJsonArray(r.locationsJson),
    employmentType: r.employmentType,
    workplaceType: r.workplaceType,
    datePosted: r.datePosted,
    salary: parseJson(r.salaryJson),
    metadata: parseJson(r.metadataJson),
    seniority: r.seniority,
    occupation: r.occupation,
    technologies: parseJsonArray(r.technologiesJson),
    status: r.status,
    boardSlug: r.boardSlug,
    monitorType: r.monitorType,
    firstSeenAt: r.firstSeenAt,
    lastSeenAt: r.lastSeenAt,
    company: {
      slug: r.companySlug,
      name: r.companyName,
      website: r.companyWebsite,
      logoUrl: r.companyLogo,
      iconUrl: r.companyIcon,
      industry: r.companyIndustry,
      employeeCountRange: r.companySize,
      foundedYear: r.companyFounded,
    },
  };
}

export async function list(q: JobsQuery) {
  const page = q.page ?? 1;
  const limit = q.limit ?? 20;
  const { sql, params } = buildWhere(q);
  const order =
    q.sort === 'oldest'
      ? 'ORDER BY j.last_seen_at ASC'
      : 'ORDER BY j.last_seen_at DESC';

  const counted = await pool.query(
    `SELECT COUNT(*)::int AS total FROM jobs j LEFT JOIN companies c ON c.slug = j.company_slug ${sql}`,
    params,
  );
  const total: number = counted.rows[0].total;

  const { rows } = await pool.query(
    `${SELECT} ${sql} ${order} LIMIT $${params.length + 1} OFFSET $${params.length + 2}`,
    [...params, limit, (page - 1) * limit],
  );
  return {
    data: rows.map(mapRow),
    meta: { total, page, limit, pages: Math.max(1, Math.ceil(total / limit)) },
  };
}

/** Open-job counts per occupation, for the role picker. */
export async function facets() {
  const { rows } = await pool.query(
    `SELECT j.occupation AS slug, COUNT(*)::int AS count
     FROM jobs j
     WHERE j.status = 'open'
       AND j.occupation IS NOT NULL
       AND j.occupation <> ''
     GROUP BY j.occupation
     ORDER BY COUNT(*) DESC, j.occupation ASC`,
  );
  return { roles: rows as Array<{ slug: string; count: number }> };
}

export async function getOne(id: number) {
  const { rows } = await pool.query(`${SELECT} WHERE j.id = $1`, [id]);
  if (!rows.length) throw new HttpError(404, 'Job not found.');
  return mapRow(rows[0]);
}
