'use client'
import { useEffect, useRef, useState, useTransition } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { roleLabel, type RoleFacet } from '@/lib/data'
import { Icon } from './ui'

const DEFAULT_SALARY_MIN = 35
const DEFAULT_SALARY_MAX = 150

// All filters live in the URL, so searches survive refresh and can be shared.
function useFilters() {
  const sp = useSearchParams(), r = useRouter(), path = usePathname(), [pending, start] = useTransition()
  // Several filter controls can change before the router commits; keep the
  // latest intended query so rapid edits compose instead of overwriting.
  const latest = useRef<URLSearchParams>(new URLSearchParams(sp.toString()))
  useEffect(() => { latest.current = new URLSearchParams(sp.toString()) }, [sp])
  useEffect(() => { document.documentElement.toggleAttribute('data-busy', pending) }, [pending])
  const set = (patch: Record<string, string | null>) => {
    const p = new URLSearchParams(latest.current.toString())
    for (const [k, v] of Object.entries(patch)) v ? p.set(k, v) : p.delete(k)
    if (!('page' in patch)) p.delete('page')
    latest.current = p
    start(() => r.replace(p.toString() ? `${path}?${p}` : path, { scroll: false }))
  }
  const clear = () => {
    latest.current = new URLSearchParams()
    start(() => r.replace(path, { scroll: false }))
  }
  return { sp, set, clear }
}

function activeCount(sp: URLSearchParams) {
  let n = ['q', 'loc', 'lvl', 'typ', 'ind', 'sch', 'co', 'types', 'roles', 'ids', 'sort'].filter(k => sp.get(k)).length
  if (sp.get('lo') && +sp.get('lo')! !== DEFAULT_SALARY_MIN) n++
  if (sp.get('hi') && +sp.get('hi')! !== DEFAULT_SALARY_MAX) n++
  return n
}

function Sel({ k, label, ph, items }: { k: string; label: string; ph: string; items: string[] }) {
  const { sp, set } = useFilters()
  return <div><label htmlFor={k}>{label}</label>
    <select id={k} className="f" value={sp.get(k) ?? ''} onChange={e => set({ [k]: e.target.value || null })}>
      <option value="">{ph}</option>{items.map(x => <option key={x}>{x}</option>)}</select></div>
}

function RolePicker({ roles }: { roles: RoleFacet[] }) {
  const { sp, set } = useFilters()
  const [selected, setSelected] = useState<string[]>(() => (sp.get('roles') ?? '').split(',').filter(Boolean))
  const [open, setOpen] = useState(false), [term, setTerm] = useState('')
  const box = useRef<HTMLDivElement>(null)
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined)
  const dirty = useRef(false)

  // Local state keeps rapid checkbox clicks from racing the router; the URL
  // catches up once the user stops clicking.
  useEffect(() => {
    if (!dirty.current) setSelected((sp.get('roles') ?? '').split(',').filter(Boolean))
  }, [sp])
  useEffect(() => () => clearTimeout(timer.current), [])

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false) }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDoc); document.removeEventListener('keydown', onKey) }
  }, [open])

  const commit = (next: string[]) => {
    dirty.current = true
    setSelected(next)
    clearTimeout(timer.current)
    timer.current = setTimeout(() => {
      dirty.current = false
      set({ roles: next.join(',') || null })
    }, 150)
  }
  const toggle = (slug: string) => commit(selected.includes(slug) ? selected.filter(x => x !== slug) : [...selected, slug])
  const shown = roles.filter(r => r.label.toLowerCase().includes(term.trim().toLowerCase()))

  return (
    <div className="rolepick" ref={box}>
      <label htmlFor="roles">Target roles</label>
      <button id="roles" type="button" className="f rolebtn" aria-expanded={open} aria-haspopup="listbox" onClick={() => setOpen(v => !v)}>
        <span>{selected.length ? `${selected.length} role${selected.length > 1 ? 's' : ''} selected` : 'All roles'}</span>
        <span className={'caret' + (open ? ' up' : '')} aria-hidden="true">⌄</span>
      </button>
      {open && <div className="roledrop">
        <input className="f" autoFocus value={term} placeholder="Search roles…" aria-label="Search roles" onChange={e => setTerm(e.target.value)} />
        <div className="rolelist" role="listbox" aria-multiselectable="true">
          {roles.length === 0
            ? <p className="rolempty">Role counts are unavailable right now.</p>
            : shown.length
              ? shown.map(r => <label className="roleopt" key={r.slug}>
                <input type="checkbox" checked={selected.includes(r.slug)} onChange={() => toggle(r.slug)} />
                <span>{r.label}</span><em>{r.count.toLocaleString()}</em>
              </label>)
              : <p className="rolempty">No roles match “{term}”.</p>}
        </div>
        <div className="rolefoot"><span>{roles.length} roles with open jobs</span>
          {selected.length ? <button type="button" className="linkbtn" onClick={() => commit([])}>Clear</button> : null}</div>
      </div>}
      {selected.length > 0 && <div className="rolechips">{selected.map(slug => {
        const r = roles.find(x => x.slug === slug)
        return <button type="button" className="chip" key={slug} onClick={() => toggle(slug)} aria-label={`Remove ${r?.label ?? slug}`}>
          {r?.label ?? roleLabel(slug)} ×</button>
      })}</div>}
    </div>
  )
}

function Keywords() {
  const { sp, set } = useFilters(), t = useRef<ReturnType<typeof setTimeout>>(undefined)
  return <div><label htmlFor="q">Keywords</label>
    <input id="q" className="f" type="search" defaultValue={sp.get('q') ?? ''} placeholder="e.g. React, fintech, growth"
      onChange={e => { const v = e.target.value; clearTimeout(t.current); t.current = setTimeout(() => set({ q: v || null }), 250) }} /></div>
}

function FilterFields({ roles }: { roles: RoleFacet[] }) {
  const { sp, set } = useFilters(), types = sp.get('types')?.split(',').filter(Boolean) ?? []
  const [lo, setLo] = useState(+(sp.get('lo') ?? DEFAULT_SALARY_MIN)), [hi, setHi] = useState(+(sp.get('hi') ?? DEFAULT_SALARY_MAX))
  // Keep the sliders in sync when filters are cleared or a shared URL is opened.
  useEffect(() => { setLo(+(sp.get('lo') ?? DEFAULT_SALARY_MIN)); setHi(+(sp.get('hi') ?? DEFAULT_SALARY_MAX)) }, [sp])
  useEffect(() => { const id = setTimeout(() => { if (lo !== +(sp.get('lo') ?? DEFAULT_SALARY_MIN) || hi !== +(sp.get('hi') ?? DEFAULT_SALARY_MAX)) set({ lo: String(lo), hi: String(hi) }) }, 200); return () => clearTimeout(id) }, [lo, hi]) // eslint-disable-line react-hooks/exhaustive-deps
  const flip = (t: string) => set({ types: (types.includes(t) ? types.filter(x => x !== t) : [...types, t]).join(',') || null })
  return <>
    <div className="spanall"><RolePicker roles={roles} /></div>
    <Sel k="loc" label="Location" ph="e.g. Remote, New York, Berlin" items={['Remote', 'New York', 'Berlin']} />
    <Sel k="lvl" label="Experience Level" ph="Select Experience Level" items={['Junior level', 'Mid level', 'Senior level']} />
    <Keywords />
    <Sel k="ind" label="Company / Industry" ph="All industries" items={['Media & Design', 'Tech', 'Retail']} />
    <Sel k="sch" label="Work Schedule" ph="Any schedule" items={['Flexible Hours', 'Shift-Based']} />
    <div><label>Job Type</label>
      <div className="chips">{['Full time', 'Part time', 'Contract'].map(t => <button key={t} type="button" className="chip" aria-pressed={types.includes(t)} onClick={() => flip(t)}>{t}</button>)}</div></div>
    <div className="salwrap">
      <div className="sal"><label style={{ margin: 0 }}>Salary Range</label><select className="f" aria-label="Period"><option>Yearly</option></select></div>
      <div className="range"><div className="fill" style={{ left: lo / 2 + '%', width: (hi - lo) / 2 + '%' }} />
        <input type="range" min={0} max={200} step={5} value={lo} aria-label="Minimum salary" onChange={e => setLo(Math.min(+e.target.value, hi))} />
        <input type="range" min={0} max={200} step={5} value={hi} aria-label="Maximum salary" onChange={e => setHi(Math.max(+e.target.value, lo))} /></div>
      <div className="rl"><span>${lo}K</span><span>${hi}K</span></div>
    </div>
  </>
}

/** One line describing the active filters, shown on the collapsed trigger. */
function summarize(sp: URLSearchParams, roles: RoleFacet[]) {
  const parts: string[] = []
  const selectedRoles = (sp.get('roles') ?? '').split(',').filter(Boolean)
    .map(slug => roles.find(r => r.slug === slug)?.label ?? roleLabel(slug))
  if (selectedRoles.length) parts.push(selectedRoles.join(', '))
  for (const key of ['loc', 'lvl', 'ind', 'sch', 'q']) {
    const v = sp.get(key)
    if (v) parts.push(v)
  }
  const types = sp.get('types')
  if (types) parts.push(types.split(',').join(', '))
  const lo = sp.get('lo'), hi = sp.get('hi')
  if ((lo && +lo !== DEFAULT_SALARY_MIN) || (hi && +hi !== DEFAULT_SALARY_MAX)) parts.push(`$${lo ?? DEFAULT_SALARY_MIN}K–$${hi ?? DEFAULT_SALARY_MAX}K`)
  return parts.join(' · ')
}

export function FilterPanel({ roles }: { roles: RoleFacet[] }) {
  const { sp, clear } = useFilters(), [open, setOpen] = useState(false), n = activeCount(sp)
  const summary = summarize(sp, roles)
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
        {n > 0 && <button type="button" className="linkbtn" onClick={clear}>Clear all</button>}
      </div>
      {/* Kept mounted so a role selection still commits if the panel is closed quickly. */}
      <div className={'panel filters' + (open ? ' filters-open' : '')} hidden={!open}>
        <div className="fgrid"><FilterFields roles={roles} /></div>
      </div>
    </div>
  )
}
