'use client'
import { useEffect, useRef, useState } from 'react'
import type { Facet } from '@/lib/data'

/** Show a facet's label, falling back to the raw slug. */
export function labelFor(options: Facet[], slug: string) {
  return options.find(o => o.slug === slug)?.label ?? slug
}

export type PickerProps = {
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

/**
 * Multi-select dropdown used by both the jobs page and the career coach.
 * It only edits the value it is given; the parent decides when to apply it.
 */
export function Picker({ id, label, placeholder, options, value, onChange, labelOf, noun }: PickerProps) {
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
