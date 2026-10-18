import { pool } from '../db/pool.js';
import { HttpError } from '../utils/http-error.js';
import type { CompaniesQuery } from '../validators/companies.validator.js';

export async function list(q: CompaniesQuery) {
  const page = q.page ?? 1;
  const limit = q.limit ?? 20;
  const conds: string[] = [];
  const params: unknown[] = [];

  if (q.search?.trim()) {
    params.push(`%${q.search.trim()}%`);
    conds.push(
      `(c.name ILIKE $${params.length} OR c.slug ILIKE $${params.length})`,
    );
  }
  if (q.industry?.trim()) {
    params.push(`%${q.industry.trim()}%`);
    conds.push(`c.industry ILIKE $${params.length}`);
  }
  const where = conds.length ? `WHERE ${conds.join(' AND ')}` : '';

  const counted = await pool.query(
    `SELECT COUNT(*)::int AS total FROM companies c ${where}`,
    params,
  );
  const total: number = counted.rows[0].total;

  const { rows } = await pool.query(
    `SELECT c.slug, c.name, c.website, c.logo_url AS "logoUrl", c.icon_url AS "iconUrl",
      c.industry, c.employee_count_range AS "employeeCountRange",
      c.founded_year AS "foundedYear",
      COUNT(j.url) FILTER (WHERE j.status = 'open')::int AS "openRoles"
    FROM companies c LEFT JOIN jobs j ON j.company_slug = c.slug AND j.status = 'open'
    ${where}
    GROUP BY c.slug
    ORDER BY "openRoles" DESC, c.name ASC
    LIMIT $${params.length + 1} OFFSET $${params.length + 2}`,
    [...params, limit, (page - 1) * limit],
  );
  return {
    data: rows,
    meta: { total, page, limit, pages: Math.max(1, Math.ceil(total / limit)) },
  };
}

export async function getOne(slug: string) {
  const { rows } = await pool.query(
    `SELECT c.slug, c.name, c.website, c.logo_url AS "logoUrl", c.icon_url AS "iconUrl",
      c.industry, c.employee_count_range AS "employeeCountRange",
      c.founded_year AS "foundedYear",
      COUNT(j.url) FILTER (WHERE j.status = 'open')::int AS "openRoles"
    FROM companies c LEFT JOIN jobs j ON j.company_slug = c.slug AND j.status = 'open'
    WHERE c.slug = $1 GROUP BY c.slug`,
    [slug],
  );
  if (!rows.length) throw new HttpError(404, 'Company not found.');

  const jobs = await pool.query(
    `SELECT id, title, seniority, occupation, locations_json AS "locationsJson", last_seen_at AS "lastSeenAt"
     FROM jobs WHERE company_slug = $1 AND status = 'open'
     ORDER BY last_seen_at DESC LIMIT 20`,
    [slug],
  );
  return { ...rows[0], jobs: jobs.rows };
}
