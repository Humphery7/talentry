'use client'
import { useEffect, useRef, useState, useTransition } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { Icon } from './ui'
// All filters live in the URL, so searches survive refresh and can be shared.
function useFilters() {
  const sp = useSearchParams(), r = useRouter(), path = usePathname(), [pending, start] = useTransition()
  useEffect(() => { document.documentElement.toggleAttribute('data-busy', pending) }, [pending])
  const set = (patch: Record<string, string | null>) => {
    const p = new URLSearchParams(sp.toString())
    for (const [k, v] of Object.entries(patch)) v ? p.set(k, v) : p.delete(k)
    start(() => r.replace(`${path}?${p}`, { scroll: false }))
  }
  return { sp, set }
}
function Sel({ k, label, ph, items }: { k: string; label: string; ph: string; items: string[] }) {
  const { sp, set } = useFilters()
  return <div><label htmlFor={k}>{label}</label>
    <select id={k} className="f" value={sp.get(k) ?? ''} onChange={e => set({ [k]: e.target.value || null })}>
      <option value="">{ph}</option>{items.map(x => <option key={x}>{x}</option>)}</select></div>
}
export function SearchBar() {
  const { sp, set } = useFilters(), t = useRef<ReturnType<typeof setTimeout>>(undefined)
  return (
    <section className="search" aria-label="Search jobs">
      <div><label htmlFor="q">Job Title / Keywords</label>
        <input id="q" className="f" type="search" defaultValue={sp.get('q') ?? ''} placeholder="e.g. UI Designer, Backend Developer"
          onChange={e => { const v = e.target.value; clearTimeout(t.current); t.current = setTimeout(() => set({ q: v || null }), 250) }} /></div>
      <Sel k="loc" label="Location" ph="e.g. Remote, New York, Berlin" items={['Remote', 'New York', 'Berlin']} />
      <Sel k="lvl" label="Experience Level" ph="Select Experience Level" items={['Junior level', 'Mid level', 'Senior level']} />
      <Sel k="typ" label="Job Type" ph="Select Job Type" items={['Full time', 'Part time', 'Contract']} />
      <div><button className="btn" onClick={() => document.getElementById('results')?.scrollIntoView({ behavior: 'smooth' })}><span style={{ display: 'flex', fontSize: 20 }}><Icon n="find" /></span>Search</button></div>
    </section>
  )
}
export function AIPanel() {
  const { set } = useFilters(), ref = useRef<HTMLInputElement>(null), [name, setName] = useState(''), [on, setOn] = useState(false)
  return (
    <div className="panel ai"><h2>Let AI find your ideal job</h2><p>Upload your CV and get matched instantly</p>
      <button className={'drop' + (on ? ' on' : '')} onClick={() => ref.current?.click()} onDragOver={e => { e.preventDefault(); setOn(true) }} onDragLeave={() => setOn(false)}
        onDrop={e => { e.preventDefault(); setOn(false); setName(e.dataTransfer.files[0]?.name ?? '') }}>
        <span className="ic"><Icon n="file" /></span><span>{name || 'Click and paste anywhere in this box.'}</span></button>
      <input ref={ref} type="file" hidden accept=".pdf,.doc,.docx" onChange={e => setName(e.target.files?.[0]?.name ?? '')} />
      <button className="btn" disabled={!name} style={{ opacity: name ? 1 : .5 }} onClick={() => set({ sort: 'int' })}>Get Matched</button></div>
  )
}
export function SidePanel() {
  const { sp, set } = useFilters(), types = sp.get('types')?.split(',').filter(Boolean) ?? []
  const [lo, setLo] = useState(+(sp.get('lo') ?? 35)), [hi, setHi] = useState(+(sp.get('hi') ?? 150))
  useEffect(() => { const id = setTimeout(() => { if (lo !== +(sp.get('lo') ?? 35) || hi !== +(sp.get('hi') ?? 150)) set({ lo: String(lo), hi: String(hi) }) }, 200); return () => clearTimeout(id) }, [lo, hi]) // eslint-disable-line react-hooks/exhaustive-deps
  const flip = (t: string) => set({ types: (types.includes(t) ? types.filter(x => x !== t) : [...types, t]).join(',') || null })
  return (
    <div className="panel filters">
      <Sel k="ind" label="Company / Industry" ph="All industries" items={['Media & Design', 'Tech', 'Retail']} />
      <Sel k="sch" label="Work Schedule" ph="Any schedule" items={['Flexible Hours', 'Shift-Based']} />
      <div className="sal"><label style={{ margin: 0 }}>Salary Range</label><select className="f" aria-label="Period"><option>Yearly</option></select></div>
      <div className="range"><div className="fill" style={{ left: lo / 2 + '%', width: (hi - lo) / 2 + '%' }} />
        <input type="range" min={0} max={200} step={5} value={lo} aria-label="Minimum salary" onChange={e => setLo(Math.min(+e.target.value, hi))} />
        <input type="range" min={0} max={200} step={5} value={hi} aria-label="Maximum salary" onChange={e => setHi(Math.max(+e.target.value, lo))} /></div>
      <div className="rl"><span>${lo}K</span><span>${hi}K</span></div>
      <label>Job Type</label>
      <div className="chips">{['Full time', 'Part time', 'Contract'].map(t => <button key={t} className="chip" aria-pressed={types.includes(t)} onClick={() => flip(t)}>{t}</button>)}</div>
    </div>
  )
}
