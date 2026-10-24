// UI job shape + URL query parsing. Data itself comes from the backend
// (see lib/api.ts) — no mock rows here anymore.
export type Job = { id: number; co: string; bg: string; ch: string; date: string; title: string; tags: string[]; min: number; max: number; loc: string; ind: string }
export interface RoleFacet { slug: string; label: string; count: number }

/* ── Company-grouped jobs ───────────────────────────── */

export interface CompanyGroup {
  name: string
  bg: string
  ch: string
  jobs: Job[]
}

/**
 * Groups a flat list of jobs by company name.
 * Preserves order based on each company's first appearance in the list.
 */
export function groupJobsByCompany(jobs: Job[]): CompanyGroup[] {
  const map = new Map<string, CompanyGroup>()

  for (const job of jobs) {
    const existing = map.get(job.co)

    if (existing) {
      existing.jobs.push(job)
    } else {
      map.set(job.co, {
        name: job.co,
        bg:   job.bg,
        ch:   job.ch,
        jobs: [job],
      })
    }
  }

  return Array.from(map.values())
}
const ACRONYMS = new Set(['ai', 'ml', 'qa', 'ux', 'ui', 'sre', 'devops', 'api', 'sdk', 'it', 'hr', 'bi', 'tpm', 'sdet', 'asic', 'ios', 'aws', 'gcp', 'sql', 'cad', 'gis', 'erp', 'crm', 'seo'])
/** `frontend-developer` -> `Frontend Developer`, `ai-engineer` -> `AI Engineer`. */
export function roleLabel(slug: string): string {
  return slug
    .split('-')
    .filter(Boolean)
    .map(w => (ACRONYMS.has(w) ? w.toUpperCase() : w[0]!.toUpperCase() + w.slice(1)))
    .join(' ')
}
export type JobQuery = { q?: string; loc?: string; lvl?: string; typ?: string; ind?: string; sch?: string; co?: string; lo?: number; hi?: number; types?: string[]; roles?: string[]; sort?: string; ids?: number[]; page?: number }
export function parseQuery(sp: Record<string, string | string[] | undefined>): JobQuery {
  const g = (k: string) => { const v = sp[k]; return (Array.isArray(v) ? v[0] : v) || undefined }
  return { q: g('q'), loc: g('loc'), lvl: g('lvl'), typ: g('typ'), ind: g('ind'), sch: g('sch'), co: g('co'), sort: g('sort'), lo: g('lo') ? +g('lo')! : undefined, hi: g('hi') ? +g('hi')! : undefined, types: g('types')?.split(','), roles: g('roles')?.split(',').filter(Boolean), ids: g('ids')?.split(',').map(Number), page: g('page') ? Math.max(1, +g('page')!) : 1 }
}
