'use client'
import { useEffect, useRef, useState, useTransition } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { roleLabel, type Facet, type JobFacets } from '@/lib/data'
import { Icon } from './ui'

const DEFAULT_SALARY_MIN = 35
const DEFAULT_SALARY_MAX = 150

/** Filters that hold several values at once. The URL stores them comma-separated. */
const LIST_KEYS = ['loc', 'lvl', 'ind', 'sch', 'types', 'roles'] as const
type ListKey = (typeof LIST_KEYS)[number]

type Draft = { q: string; lo: number; hi: number } & Record<ListKey, string[]>

const splitList = (v: string | null) => (v ?? '').split(',').map(s => s.trim()).filter(Boolean)

/** The panel edits a draft; nothing reaches the URL until "Apply filters". */
function readDraft(sp: URLSearchParams): Draft {
  return {
    q: sp.get('q') ?? '',
    lo: +(sp.get('lo') ?? DEFAULT_SALARY_MIN),
    hi: +(sp.get('hi') ?? DEFAULT_SALARY_MAX),
    loc: splitList(sp.get('loc')),
    lvl: splitList(sp.get('lvl')),
    ind: splitList(sp.get('ind')),
    sch: splitList(sp.get('sch')),
    types: splitList(sp.get('types')),
    roles: splitList(sp.get('roles')),
  }
}

/** Draft -> URL. Params this panel does not own (`co`, `sort`, `ids`) are kept. */
function toQuery(sp: URLSearchParams, d: Draft) {
  const p = new URLSearchParams(sp.toString())
  for (const k of LIST_KEYS) d[k].length ? p.set(k, d[k].join(',')) : p.delete(k)
  d.q.trim() ? p.set('q', d.q.trim()) : p.delete('q')
  d.lo !== DEFAULT_SALARY_MIN ? p.set('lo', String(d.lo)) : p.delete('lo')
  d.hi !== DEFAULT_SALARY_MAX ? p.set('hi', String(d.hi)) : p.delete('hi')
  p.delete('page')
  return p
}

/** How many controls differ from what is currently applied. */
function changedCount(sp: URLSearchParams, d: Draft) {
  const a = readDraft(sp)
  let n = 0
  if (a.q !== d.q) n++
  if (a.lo !== d.lo || a.hi !== d.hi) n++
  for (const k of LIST_KEYS) if (a[k].join(',') !== d[k].join(',')) n++
  return n
}

function useFilters() {
  const sp = useSearchParams(), r = useRouter(), path = usePathname(), [pending, start] = useTransition()
  useEffect(() => { document.documentElement.toggleAttribute('data-busy', pending) }, [pending])
  const apply = (d: Draft) => {
    const p = toQuery(sp, d)
    start(() => r.replace(p.toString() ? `${path}?${p}` : path, { scroll: false }))
  }
  const clearAll = () => start(() => r.replace(path, { scroll: false }))
  return { sp, apply, clearAll }
}

function activeCount(sp: URLSearchParams) {
  let n = ['q', 'loc', 'lvl', 'typ', 'ind', 'sch', 'co', 'types', 'roles', 'ids', 'sort'].filter(k => sp.get(k)).length
  if (sp.get('lo') && +sp.get('lo')! !== DEFAULT_SALARY_MIN) n++
  if (sp.get('hi') && +sp.get('hi')! !== DEFAULT_SALARY_MAX) n++
  return n
}

function labelFor(options: Facet[], slug: string) {
  return options.find(o => o.slug === slug)?.label ?? slug
}

type PickerProps = {
  id: string
  label: string
  placeholder: string
  options: Facet[]
  value: string[]
  onChange: (next: string[]) => void
  /** Roles are labelled from the slug when the API sends no label. */
  labelOf?: (slug: string) => string
  noun: string
}

function Picker({ id, label, placeholder, options, value, onChange, labelOf, noun }: PickerProps) {
  const [open, setOpen] = useState(false), [term, setTerm] = useState('')
  const box = useRef<HTMLDivElement>(null)
  const labelText = labelOf ?? ((slug: string) => labelFor(options, slug))

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false) }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDoc); document.removeEventListener('keydown', onKey) }
  }, [open])

  const toggle = (slug: string) =>
    onChange(value.includes(slug) ? value.filter(x => x !== slug) : [...value, slug])
  const shown = term.trim()
    ? options.filter(o => labelText(o.slug).toLowerCase().includes(term.trim().toLowerCase()))
    : options

  return (
    <div className="rolepick" ref={box}>
      <label htmlFor={id}>{label}</label>
      <button id={id} type="button" className="f rolebtn" aria-expanded={open} aria-haspopup="listbox" onClick={() => setOpen(v => !v)}>
        <span>{value.length ? `${value.length} ${noun}${value.length > 1 ? 's' : ''} selected` : placeholder}</span>
        <span className={'caret' + (open ? ' up' : '')} aria-hidden="true">⌄</span>
      </button>
      {open && <div className="roledrop">
        {options.length > 8 && (
          <input className="f" autoFocus value={term} placeholder={`Search ${label.toLowerCase()}…`} aria-label={`Search ${label}`} onChange={e => setTerm(e.target.value)} />
        )}
        <div className="rolelist" role="listbox" aria-multiselectable="true">
          {shown.length
            ? shown.map(o => <label className="roleopt" key={o.slug}>
              <input type="checkbox" checked={value.includes(o.slug)} onChange={() => toggle(o.slug)} />
              <span>{labelText(o.slug)}</span>{o.count > 0 && <em>{o.count.toLocaleString()}</em>}
            </label>)
            : <p className="rolempty">{options.length ? `No matches for “${term}”.` : 'Options are unavailable right now.'}</p>}
        </div>
        <div className="rolefoot"><span>{options.length} option{options.length === 1 ? '' : 's'}</span>
          {value.length ? <button type="button" className="linkbtn" onClick={() => onChange([])}>Clear</button> : null}</div>
      </div>}
      {value.length > 0 && <div className="rolechips">{value.map(slug =>
        <button type="button" className="chip" key={slug} onClick={() => toggle(slug)} aria-label={`Remove ${labelText(slug)}`}>
          {labelText(slug)} ×</button>)}</div>}
    </div>
  )
}

function Keywords({ value, onChange, onApply }: { value: string; onChange: (v: string) => void; onApply: () => void }) {
  return <div><label htmlFor="q">Keywords</label>
    <input id="q" className="f" type="search" value={value} placeholder="e.g. React, fintech, growth"
      onChange={e => onChange(e.target.value)}
      onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); onApply() } }} /></div>
}

/** Shown when the API cannot supply counts, so the filters still work. */
const FALLBACK: Pick<JobFacets, 'locations' | 'levels' | 'workplaces' | 'types'> = {
  locations: [
    ['us', 'United States'], ['europe', 'Europe'], ['india', 'India'], ['apac', 'Asia-Pacific'],
    ['canada', 'Canada'], ['latam', 'Latin America'], ['mena', 'Middle East & Africa'], ['other', 'Other'],
  ].map(([slug, label]) => ({ slug, label, count: 0 })),
  levels: ['Junior level', 'Mid level', 'Senior level'].map(label => ({ slug: label, label, count: 0 })),
  workplaces: [['remote', 'Remote'], ['hybrid', 'Hybrid'], ['onsite', 'On-site']].map(([slug, label]) => ({ slug, label, count: 0 })),
  types: [['fulltime', 'Full time'], ['parttime', 'Part time'], ['contract', 'Contract'], ['internshipcoop', 'Internship']].map(([slug, label]) => ({ slug, label, count: 0 })),
}

function FilterFields({ facets, draft, setDraft, onApply }: {
  facets: JobFacets
  draft: Draft
  setDraft: (d: Draft) => void
  onApply: () => void
}) {
  const patch = (p: Partial<Draft>) => setDraft({ ...draft, ...p })
  const locations = facets.locations.length ? facets.locations : FALLBACK.locations
  const levels = facets.levels.length ? facets.levels : FALLBACK.levels
  const workplaces = facets.workplaces.length ? facets.workplaces : FALLBACK.workplaces
  const types = facets.types.length ? facets.types : FALLBACK.types

  const toggleType = (slug: string) =>
    patch({ types: draft.types.includes(slug) ? draft.types.filter(t => t !== slug) : [...draft.types, slug] })

  return <>
    <div className="spanall">
      <Picker id="roles" label="Target roles" placeholder="All roles" options={facets.roles} noun="role"
        value={draft.roles} onChange={roles => patch({ roles })} labelOf={slug => labelFor(facets.roles, slug) || roleLabel(slug)} />
    </div>

    <Keywords value={draft.q} onChange={q => patch({ q })} onApply={onApply} />

    <Picker id="loc" label="Location" placeholder="All locations" options={locations} noun="location"
      value={draft.loc} onChange={loc => patch({ loc })} />

    <Picker id="lvl" label="Experience Level" placeholder="Any level" options={levels} noun="level"
      value={draft.lvl} onChange={lvl => patch({ lvl })} />

    <Picker id="ind" label="Company / Industry" placeholder="All industries" options={facets.industries} noun="industry"
      value={draft.ind} onChange={ind => patch({ ind })} />

    <Picker id="sch" label="Workplace" placeholder="Remote, hybrid, on-site" options={workplaces} noun="workplace"
      value={draft.sch} onChange={sch => patch({ sch })} />

    <div><label>Job Type</label>
      <div className="chips">{types.map(t => <button key={t.slug} type="button" className="chip" aria-pressed={draft.types.includes(t.slug)} onClick={() => toggleType(t.slug)}>{t.label}</button>)}</div></div>

    <div className="salwrap">
      <div className="sal"><label style={{ margin: 0 }}>Salary Range</label><select className="f" aria-label="Period"><option>Yearly</option></select></div>
      <div className="range"><div className="fill" style={{ left: draft.lo / 2 + '%', width: (draft.hi - draft.lo) / 2 + '%' }} />
        <input type="range" min={0} max={200} step={5} value={draft.lo} aria-label="Minimum salary" onChange={e => patch({ lo: Math.min(+e.target.value, draft.hi) })} />
        <input type="range" min={0} max={200} step={5} value={draft.hi} aria-label="Maximum salary" onChange={e => patch({ hi: Math.max(+e.target.value, draft.lo) })} /></div>
      <div className="rl"><span>${draft.lo}K</span><span>${draft.hi}K</span></div>
    </div>
  </>
}

/** One line describing the applied filters, shown on the collapsed trigger. */
function summarize(sp: URLSearchParams, facets: JobFacets) {
  const parts: string[] = []
  const q = sp.get('q')
  if (q) parts.push(q)

  const roles = splitList(sp.get('roles')).map(slug => labelFor(facets.roles, slug) || roleLabel(slug))
  if (roles.length) parts.push(roles.join(', '))

  const locations = splitList(sp.get('loc')).map(slug => labelFor(facets.locations, slug))
  if (locations.length) parts.push(locations.join(', '))

  const levels = splitList(sp.get('lvl')).map(slug => labelFor(facets.levels, slug))
  if (levels.length) parts.push(levels.join(', '))

  const industries = splitList(sp.get('ind')).map(slug => labelFor(facets.industries, slug))
  if (industries.length) parts.push(industries.join(', '))

  const workplaces = splitList(sp.get('sch')).map(slug => labelFor(facets.workplaces, slug))
  if (workplaces.length) parts.push(workplaces.join(', '))

  const types = splitList(sp.get('types')).map(slug => labelFor(facets.types, slug))
  if (types.length) parts.push(types.join(', '))

  const lo = sp.get('lo'), hi = sp.get('hi')
  if ((lo && +lo !== DEFAULT_SALARY_MIN) || (hi && +hi !== DEFAULT_SALARY_MAX)) {
    parts.push(`$${lo ?? DEFAULT_SALARY_MIN}K–$${hi ?? DEFAULT_SALARY_MAX}K`)
  }
  return parts.join(' · ')
}

export function FilterPanel({ facets }: { facets: JobFacets }) {
  const { sp, apply, clearAll } = useFilters()
  const [open, setOpen] = useState(false)
  const key = sp.toString()
  const [draft, setDraft] = useState<Draft>(() => readDraft(sp))
  // A new URL (Clear all, back button, a shared link) resets the draft.
  useEffect(() => { setDraft(readDraft(sp)) }, [key]) // eslint-disable-line react-hooks/exhaustive-deps

  const n = activeCount(sp)
  const summary = summarize(sp, facets)
  const changes = changedCount(sp, draft)
  const submit = () => { apply(draft); setOpen(false) }
  const reset = () => { const d = readDraft(new URLSearchParams()); setDraft(d); apply(d) }

  return (
    <div className="filterbar">
      <div className="filterbar-row">
        <button type="button" className="searchtrigger" aria-expanded={open} onClick={() => setOpen(v => !v)}>
          <span className="stic"><Icon n="find" /></span>
          <span className={'sttext' + (summary ? ' on' : '')}>{summary || 'Search by role, location or experience'}</span>
          <span className="stfilters"><Icon n="set" /><span>Filters</span>
            {n > 0 && <span className="badge">{n}</span>}
            <span className={'caret' + (open ? ' up' : '')} aria-hidden="true">⌄</span></span>
        </button>
        {n > 0 && <button type="button" className="linkbtn" onClick={clearAll}>Clear all</button>}
      </div>
      {/* Kept mounted so a draft survives closing and reopening the panel. */}
      <div className={'panel filters' + (open ? ' filters-open' : '')} hidden={!open}>
        <div className="fgrid">
          <FilterFields facets={facets} draft={draft} setDraft={setDraft} onApply={submit} />
          <div className="filterapply">
            <span className="fhint">
              {changes ? `${changes} change${changes === 1 ? '' : 's'} not applied yet` : 'Pick as many as you like, then apply once.'}
            </span>
            <span className="factions">
              <button type="button" className="linkbtn" onClick={reset}>Clear</button>
              <button type="button" className="btn" onClick={submit} disabled={!changes}>
                {changes ? 'Apply filters' : 'Filters applied'}
              </button>
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
