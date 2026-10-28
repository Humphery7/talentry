// The single seam between UI and backend. Server pages call these;
// they fetch the NestJS API (API_URL server-side, default localhost:3001).
import { roleLabel, type Job, type JobQuery, type RoleFacet } from './data'

const API_BASE = process.env.API_URL ?? 'http://localhost:3001'

export interface BackendCompany {
  slug: string; name: string; website: string | null; logoUrl: string | null;
  iconUrl: string | null; industry: string | null; employeeCountRange: string | null;
  foundedYear: number | null; openRoles?: number
}
export interface BackendJob {
  id: number; url: string; title: string; locations: string[]; employmentType: string | null;
  workplaceType: string | null; datePosted: string | null; lastSeenAt: string;
  salary: unknown; seniority: string | null; occupation: string | null;
  company: { slug: string; name: string | null; industry: string | null }
}

const prettyType = (t: string | null) =>
  !t ? null : t.replace(/([a-z])([A-Z])/g, '$1 $2').replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim() || null
const LEVEL_LABEL: Record<string, string> = {
  entry: 'Junior level', junior: 'Junior level', mid: 'Mid level',
  senior: 'Senior level', staff: 'Senior level', principal: 'Senior level',
  director: 'Senior level', lead: 'Senior level',
}
/** Backend salary values are treated as $K; raw dollar figures are scaled down. */
function toK(v: unknown): number {
  const n = typeof v === 'number' ? v : Number(v)
  if (!Number.isFinite(n) || n <= 0) return 0
  return n > 5000 ? Math.round(n / 1000) : Math.round(n)
}
function salaryRange(s: unknown): [number, number] {
  if (typeof s === 'number') return [toK(s), toK(s)]
  if (s && typeof s === 'object') {
    const o = s as Record<string, unknown>
    const lo = o.min ?? o.salary_min ?? o.min_salary ?? o.low ?? o.amount ?? o.value ?? 0
    const hi = o.max ?? o.salary_max ?? o.max_salary ?? o.high ?? o.amount ?? o.value ?? lo
    return [toK(lo), toK(hi)]
  }
  return [0, 0]
}
const bgFor = (name: string) => {
  let h = 0
  for (const c of name) h = (h * 31 + c.charCodeAt(0)) % 360
  return `hsl(${h} 45% 32%)`
}
const initials = (name: string) =>
  name.split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0]!.toUpperCase()).join('') || '?'
const fmtDate = (iso: string | null) => {
  if (!iso) return ''
  const d = new Date(iso)
  return Number.isNaN(+d) ? '' : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

export function mapJob(b: BackendJob): Job {
  const co = b.company.name ?? b.company.slug
  const [min, max] = salaryRange(b.salary)
  const lvl = b.seniority ? (LEVEL_LABEL[b.seniority.toLowerCase()] ?? b.seniority) : null
  return {
    id: b.id, url: b.url, co, bg: bgFor(co), ch: initials(co),
    date: fmtDate(b.datePosted ?? b.lastSeenAt), title: b.title ?? '(untitled)',
    tags: [prettyType(b.employmentType), b.workplaceType, lvl, b.occupation].filter(Boolean) as string[],
    min, max,
    loc: b.locations[0] ?? 'Unspecified', ind: b.company.industry ?? '',
  }
}

function params(q: JobQuery): string {
  const p = new URLSearchParams()
  const put = (k: string, v: unknown) => {
    if (v === undefined || v === null || v === '') return
    p.set(k, Array.isArray(v) ? v.join(',') : String(v))
  }
  put('q', q.q); put('loc', q.loc); put('lvl', q.lvl); put('typ', q.typ); put('ind', q.ind)
  put('sch', q.sch); put('co', q.co); put('sort', q.sort); put('ids', q.ids); put('roles', q.roles)
  if (q.lo !== undefined) p.set('lo', String(q.lo))
  if (q.hi !== undefined) p.set('hi', String(q.hi))
  if (q.types?.length) p.set('types', q.types.join(','))
  if (q.page && q.page > 1) p.set('page', String(q.page))
  // The jobs page groups results by company after fetching. A small page size
  // lets one company with many roles fill the whole page, so ask for the API
  // maximum and let each company card scroll internally.
  p.set('limit', '100')
  return p.toString()
}

export async function getJobs(q: JobQuery): Promise<{ jobs: Job[]; total: number; pages: number }> {
  const r = await fetch(`${API_BASE}/jobs?${params(q)}`, { cache: 'no-store' })
  if (!r.ok) throw new Error(`Backend ${r.status}`)
  const d = await r.json()
  return { jobs: (d.data as BackendJob[]).map(mapJob), total: d.meta.total, pages: d.meta.pages }
}

/** Open-job counts per occupation, straight from the crawler's labels. */
export async function getRoleFacets(): Promise<RoleFacet[]> {
  try {
    // Counts change slowly; avoid re-running the GROUP BY on every page view.
    const r = await fetch(`${API_BASE}/jobs/facets`, { next: { revalidate: 60 } })
    if (!r.ok) return []
    const d = (await r.json()) as { roles?: Array<{ slug: string; count: number }> }
    return (d.roles ?? []).map(role => ({ ...role, label: roleLabel(role.slug) }))
  } catch {
    return []
  }
}

export async function getJob(id: number): Promise<Job | undefined> {
  const r = await fetch(`${API_BASE}/jobs/${id}`, { cache: 'no-store' })
  if (r.status === 404) return undefined
  if (!r.ok) throw new Error(`Backend ${r.status}`)
  return mapJob(await r.json() as BackendJob)
}

export async function getCompanies(): Promise<BackendCompany[]> {
  const r = await fetch(`${API_BASE}/companies?limit=100`, { cache: 'no-store' })
  if (!r.ok) throw new Error(`Backend ${r.status}`)
  return (await r.json()).data as BackendCompany[]
}

export interface LiveCounts {
  openJobs: number
  companies: number
}

/** Real totals for the About page. Returns null when the API is unreachable. */
export async function getLiveCounts(): Promise<LiveCounts | null> {
  try {
    const [jobs, companies] = await Promise.all([
      fetch(`${API_BASE}/jobs?status=open&limit=1`, { cache: 'no-store' }),
      fetch(`${API_BASE}/companies?limit=1`, { cache: 'no-store' }),
    ])
    if (!jobs.ok || !companies.ok) return null
    const j = (await jobs.json()) as { meta?: { total?: number } }
    const c = (await companies.json()) as { meta?: { total?: number } }
    return {
      openJobs: Number(j.meta?.total ?? 0),
      companies: Number(c.meta?.total ?? 0),
    }
  } catch {
    return null
  }
}
