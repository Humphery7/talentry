import { pool } from '../db/pool.js';
import { HttpError } from '../utils/http-error.js';
import type { JobsQuery } from '../validators/jobs.validator.js';
import {
  ALL_LOCATION_REGEX,
  REGION_BY_SLUG,
  REGION_REGEXES,
  WORKPLACE_LOCATION_PATTERNS,
} from './job-locations.js';

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
  'senior level': ['senior', 'staff', 'principal', 'director', 'lead', 'executive'],
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
const normType = (t: string) => t.toLowerCase().replace(/[^a-z0-9]+/g, '');

/** Workplace values ("OnSite", "on-site") and the filter share one spelling. */
const normWorkplace = (w: string) => w.toLowerCase().replace(/[^a-z0-9]+/g, '');

/** The filter sends comma-separated lists; older links send one value. */
const listOf = (raw?: string): string[] =>
  (raw ?? '')
    .split(',')
    .map((v) => v.trim())
    .filter(Boolean);

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
/**
 * Region slug -> the exact location strings that belong to it. Built once from
 * the distinct locations in the table, then reused: matching 4,500 strings by
 * equality is far cheaper than running a regex against 140,000 of them.
 */
let locationIndex: { at: number; byRegion: Map<string, string[]> } | null = null;

export async function getLocationIndex(): Promise<Map<string, string[]>> {
  if (locationIndex && Date.now() - locationIndex.at < FACET_TTL_MS) {
    return locationIndex.byRegion;
  }
  const { rows } = await pool.query(
    `WITH open_locs AS MATERIALIZED (
       SELECT DISTINCT loc.loc
       FROM jobs j
       CROSS JOIN LATERAL jsonb_array_elements_text((j.locations_json)::jsonb) AS loc(loc)
       WHERE j.status = 'open' AND j.locations_json IS NOT NULL
     )
     SELECT DISTINCT l.loc, p.slug
     FROM open_locs l
     JOIN unnest($1::text[], $2::text[]) AS p(slug, pattern)
       ON l.loc ~* p.pattern`,
    [
      REGION_REGEXES.map((r) => r.slug),
      REGION_REGEXES.map((r) => r.pattern),
    ],
  );
  const byRegion = new Map<string, string[]>(
    REGION_REGEXES.map((r) => [r.slug, []]),
  );
  for (const row of rows as Array<{ loc: string; slug: string }>) {
    byRegion.get(row.slug)?.push(row.loc);
  }
  locationIndex = { at: Date.now(), byRegion };
  return byRegion;
}

export function buildWhere(
  q: JobsQuery,
  regionLocs?: Map<string, string[]>,
): { sql: string; params: unknown[] } {
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
  if (q.ind?.trim()) {
    const industries = listOf(q.ind).map((v) => `%${v}%`);
    if (industries.length) conds.push(`c.industry ILIKE ANY(${p(industries)})`);
  }
  if (q.loc?.trim()) {
    // Region slugs ("us", "europe") match a group of patterns; anything else
    // is treated as free text so old links like `loc=Berlin` keep working.
    const regexes: string[] = [];
    const likes: string[] = [];
    const exact: string[] = [];
    let wantsOther = false;
    for (const value of listOf(q.loc)) {
      const key = value.toLowerCase();
      if (key === 'other') wantsOther = true;
      else {
        const region = REGION_BY_SLUG[key];
        const known = regionLocs?.get(key);
        if (known?.length) exact.push(...known);
        else if (region) regexes.push(region.pattern);
        else likes.push(`%${value}%`);
      }
    }
    const parts: string[] = [];
    if (exact.length) {
      parts.push(
        `EXISTS (
           SELECT 1 FROM jsonb_array_elements_text((j.locations_json)::jsonb) AS loc(loc)
           WHERE loc.loc = ANY(${p(exact)})
         )`,
      );
    }
    if (regexes.length) {
      parts.push(
        `EXISTS (
           SELECT 1 FROM jsonb_array_elements_text((j.locations_json)::jsonb) AS loc(loc)
           WHERE loc.loc ~* ANY(${p(regexes)})
         )`,
      );
    }
    if (likes.length) {
      parts.push(
        `EXISTS (
           SELECT 1 FROM jsonb_array_elements_text((j.locations_json)::jsonb) AS loc(loc)
           WHERE loc.loc ILIKE ANY(${p(likes)})
         )`,
      );
    }
    if (wantsOther) {
      parts.push(
        `NOT EXISTS (
           SELECT 1 FROM jsonb_array_elements_text((j.locations_json)::jsonb) AS loc(loc)
           WHERE loc.loc ~* ${p(ALL_LOCATION_REGEX)}
         )`,
      );
    }
    if (parts.length) {
      conds.push(`j.locations_json IS NOT NULL AND (${parts.join(' OR ')})`);
    }
  }
  if (q.lvl?.trim()) {
    const levels = listOf(q.lvl).flatMap(
      (value) => LEVEL_MAP[value.toLowerCase()] ?? [value.toLowerCase()],
    );
    if (levels.length) conds.push(`lower(j.seniority) = ANY(${p(levels)})`);
  }
  if (q.roles?.trim()) {
    const roles = listOf(q.roles).map((r) => r.toLowerCase());
    if (roles.length) conds.push(`lower(j.occupation) = ANY(${p(roles)})`);
  }
  const typeList = [
    ...(q.typ?.trim() ? [q.typ.trim()] : []),
    ...listOf(q.types),
  ];
  if (typeList.length) {
    // Contains, not equality, so "Internship" also finds "Internship/Co-op".
    conds.push(
      `regexp_replace(lower(COALESCE(j.employment_type, '')), '[^a-z0-9]+', '', 'g')
         LIKE ANY(${p(typeList.map((t) => `%${normType(t)}%`))})`,
    );
  }
  if (q.sch?.trim()) {
    // "Workplace": remote / hybrid / onsite. Workplace type is often missing,
    // so the location text is used as a fallback ("Remote", "San Mateo Hybrid").
    const workplaces = listOf(q.sch).map(normWorkplace);
    const ors: string[] = [];
    if (workplaces.length) {
      ors.push(
        `regexp_replace(lower(COALESCE(j.workplace_type, '')), '[^a-z0-9]+', '', 'g')
           = ANY(${p(workplaces)})`,
      );
    }
    const locationPatterns = workplaces.flatMap(
      (w) => WORKPLACE_LOCATION_PATTERNS[w] ?? [],
    );
    if (locationPatterns.length) {
      ors.push(
        `EXISTS (
           SELECT 1 FROM jsonb_array_elements_text((j.locations_json)::jsonb) AS loc(loc)
           WHERE loc.loc ILIKE ANY(${p(locationPatterns)})
         )`,
      );
    }
    if (ors.length) conds.push(`(${ors.join(' OR ')})`);
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
  // Region filters are resolved against the cached location index so the query
  // compares strings instead of running a regex over every job.
  let regionLocs: Map<string, string[]> | undefined;
  if (q.loc?.trim()) {
    try {
      regionLocs = await getLocationIndex();
    } catch {
      regionLocs = undefined; // fall back to the regex path
    }
  }
  const { sql, params } = buildWhere(q, regionLocs);
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

/** Facet counts change slowly and cost a full scan, so keep them for a while. */
const FACET_TTL_MS = 10 * 60 * 1000;
let facetCache: { at: number; data: Facets } | null = null;

export interface Facets {
  roles: Array<{ slug: string; count: number }>;
  locations: Array<{ slug: string; label: string; count: number }>;
  industries: Array<{ slug: string; label: string; count: number }>;
  levels: Array<{ slug: string; label: string; count: number }>;
  workplaces: Array<{ slug: string; label: string; count: number }>;
  types: Array<{ slug: string; label: string; count: number }>;
}

/**
 * Counts for every filter menu.
 *
 * Locations are grouped into regions, and the counts overlap on purpose: a job
 * that is both "Remote" and "United States" counts in both, and a job listing
 * three US cities still counts once for the United States.
 *
 * The query classifies the *distinct* location strings first (about 10k), then
 * joins them back to jobs. Running the regex against all 140k location values
 * instead takes minutes, not milliseconds.
 */
export async function facets(): Promise<Facets> {
  if (facetCache && Date.now() - facetCache.at < FACET_TTL_MS) {
    return facetCache.data;
  }

  const regionSlugs = REGION_REGEXES.map((r) => r.slug);
  const regionPatterns = REGION_REGEXES.map((r) => r.pattern);

  // Sequential on purpose: the pool allows five connections and these scans are
  // heavy. Parallelising them just makes every request queue for a connection.
  const roles = await pool.query(
    `SELECT j.occupation AS slug, COUNT(*)::int AS count
     FROM jobs j
     WHERE j.status = 'open'
       AND j.occupation IS NOT NULL
       AND j.occupation <> ''
     GROUP BY j.occupation
     ORDER BY COUNT(*) DESC, j.occupation ASC`,
  );

  const locations = await pool.query(
    `WITH open_locs AS MATERIALIZED (
       SELECT DISTINCT loc.loc
       FROM jobs j
       CROSS JOIN LATERAL jsonb_array_elements_text((j.locations_json)::jsonb) AS loc(loc)
       WHERE j.status = 'open' AND j.locations_json IS NOT NULL
     ),
     classified AS MATERIALIZED (
       SELECT DISTINCT l.loc, p.slug
       FROM open_locs l
       JOIN unnest($1::text[], $2::text[]) AS p(slug, pattern)
         ON l.loc ~* p.pattern
     ),
     job_regions AS MATERIALIZED (
       SELECT DISTINCT j.id, c.slug
       FROM jobs j
       CROSS JOIN LATERAL jsonb_array_elements_text((j.locations_json)::jsonb) AS loc(loc)
       JOIN classified c ON c.loc = loc.loc
       WHERE j.status = 'open'
     )
     SELECT slug, COUNT(*)::int AS count
     FROM job_regions
     GROUP BY slug`,
    [regionSlugs, regionPatterns],
  );

  const industries = await pool.query(
    `SELECT c.industry AS label, COUNT(*)::int AS count
     FROM jobs j
     JOIN companies c ON c.slug = j.company_slug
     WHERE j.status = 'open'
       AND c.industry IS NOT NULL
       AND c.industry <> ''
     GROUP BY c.industry
     ORDER BY COUNT(*) DESC, c.industry ASC`,
  );

  const levels = await pool.query(
    `SELECT level AS label, COUNT(*)::int AS count
     FROM (
       SELECT CASE
         WHEN lower(j.seniority) IN ('entry', 'junior') THEN 'Junior level'
         WHEN lower(j.seniority) = 'mid' THEN 'Mid level'
         WHEN lower(j.seniority) IN ('senior', 'staff', 'principal', 'director', 'lead', 'executive')
           THEN 'Senior level'
       END AS level
       FROM jobs j
       WHERE j.status = 'open'
     ) t
     WHERE level IS NOT NULL
     GROUP BY level
     ORDER BY count DESC`,
  );

  const WORKPLACE_LABELS: Record<string, string> = {
    remote: 'Remote',
    hybrid: 'Hybrid',
    onsite: 'On-site',
  };
  const workplaceRows: Array<{ slug: string; count: number }> = [];
  for (const [slug, label] of Object.entries(WORKPLACE_LABELS)) {
    const patterns = WORKPLACE_LOCATION_PATTERNS[slug] ?? [];
    const row = await pool.query(
      `SELECT COUNT(*)::int AS count
       FROM jobs j
       WHERE j.status = 'open'
         AND (
           regexp_replace(lower(COALESCE(j.workplace_type, '')), '[^a-z0-9]+', '', 'g') = $1
           OR EXISTS (
             SELECT 1 FROM jsonb_array_elements_text((j.locations_json)::jsonb) AS loc(loc)
             WHERE loc.loc ILIKE ANY($2::text[])
           )
         )`,
      [slug, patterns],
    );
    workplaceRows.push({ slug, count: Number(row.rows[0]?.count ?? 0) });
  }

  const types = await pool.query(
    `SELECT regexp_replace(lower(COALESCE(j.employment_type, '')), '[^a-z0-9]+', '', 'g') AS slug,
            COUNT(*)::int AS count
     FROM jobs j
     WHERE j.status = 'open'
       AND j.employment_type IS NOT NULL
       AND j.employment_type <> ''
     GROUP BY 1
     ORDER BY count DESC`,
  );

  const locationCounts = new Map<string, number>(
    (locations.rows as Array<{ slug: string; count: number }>).map((r) => [
      r.slug,
      r.count,
    ]),
  );

  const TYPE_LABELS: Record<string, string> = {
    fulltime: 'Full time',
    parttime: 'Part time',
    contract: 'Contract',
    internshipcoop: 'Internship',
    employeepermanent: 'Permanent',
    temporary: 'Temporary',
    freelance: 'Freelance',
  };
  const data: Facets = {
    roles: roles.rows as Array<{ slug: string; count: number }>,
    locations: REGION_REGEXES.map((r) => ({
      slug: r.slug,
      label: r.label,
      count: locationCounts.get(r.slug) ?? 0,
    })).filter((r) => r.count > 0),
    industries: (industries.rows as Array<{ label: string; count: number }>).map(
      (r) => ({ slug: r.label, label: r.label, count: r.count }),
    ),
    levels: (levels.rows as Array<{ label: string; count: number }>).map((r) => ({
      slug: r.label,
      label: r.label,
      count: r.count,
    })),
    workplaces: workplaceRows
      .filter((r) => r.count > 0)
      .map((r) => ({
        slug: r.slug,
        label: WORKPLACE_LABELS[r.slug]!,
        count: r.count,
      })),
    types: (types.rows as Array<{ slug: string; count: number }>)
      .filter((r) => TYPE_LABELS[r.slug])
      .map((r) => ({ slug: r.slug, label: TYPE_LABELS[r.slug]!, count: r.count })),
  };

  facetCache = { at: Date.now(), data };
  return data;
}

export async function getOne(id: number) {
  const { rows } = await pool.query(`${SELECT} WHERE j.id = $1`, [id]);
  if (!rows.length) throw new HttpError(404, 'Job not found.');
  return mapRow(rows[0]);
}
