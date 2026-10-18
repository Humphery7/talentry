// UI job shape + URL query parsing. Data itself comes from the backend
// (see lib/api.ts) — no mock rows here anymore.
export type Job = { id: number; co: string; bg: string; ch: string; date: string; title: string; tags: string[]; min: number; max: number; app: number; int: number; loc: string; ind: string }
export type JobQuery = { q?: string; loc?: string; lvl?: string; typ?: string; ind?: string; sch?: string; co?: string; lo?: number; hi?: number; types?: string[]; sort?: string; ids?: number[]; page?: number }
export function parseQuery(sp: Record<string, string | string[] | undefined>): JobQuery {
  const g = (k: string) => { const v = sp[k]; return (Array.isArray(v) ? v[0] : v) || undefined }
  return { q: g('q'), loc: g('loc'), lvl: g('lvl'), typ: g('typ'), ind: g('ind'), sch: g('sch'), co: g('co'), sort: g('sort'), lo: g('lo') ? +g('lo')! : 35, hi: g('hi') ? +g('hi')! : 150, types: g('types')?.split(','), ids: g('ids')?.split(',').map(Number), page: g('page') ? Math.max(1, +g('page')!) : 1 }
}
