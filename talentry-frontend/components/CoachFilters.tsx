'use client'
import { useEffect, useState } from 'react'
import { roleLabel, type JobFacets } from '@/lib/data'
import type { RecommendationFilters } from '@/lib/recommendations'
import { FILTER_FALLBACK } from './Filters'
import { Picker, labelFor } from './Picker'
import { Icon } from './ui'

const LIST_KEYS = ['loc', 'lvl', 'ind', 'sch', 'types', 'roles'] as const
type ListKey = (typeof LIST_KEYS)[number]
type Draft = { q: string } & Record<ListKey, string[]>

const asList = (value: string[] | undefined) => (Array.isArray(value) ? value : [])

function toDraft(filters: RecommendationFilters): Draft {
  return {
    q: filters.q ?? '',
    loc: asList(filters.loc),
    lvl: asList(filters.lvl),
    ind: asList(filters.ind),
    sch: asList(filters.sch),
    types: asList(filters.types),
    roles: asList(filters.roles),
  }
}

/** Draft -> API payload, dropping empty values so `{}` means "all jobs". */
function toFilters(draft: Draft): RecommendationFilters {
  const out: RecommendationFilters = {}
  for (const key of LIST_KEYS) {
    if (draft[key].length) out[key] = draft[key]
  }
  const q = draft.q.trim()
  if (q) out.q = q
  return out
}

/**
 * Key order from JSONB is not stable, so compare a canonical form instead of
 * the raw JSON. Otherwise an unchanged scope looks dirty after every reload.
 */
function canonical(filters: RecommendationFilters): string {
  const out: Record<string, unknown> = {}
  for (const key of LIST_KEYS) {
    if (filters[key]?.length) out[key] = filters[key]
  }
  if (filters.q?.trim()) out.q = filters.q.trim()
  return JSON.stringify(out)
}

function summarize(filters: RecommendationFilters, facets: JobFacets): string {
  const parts: string[] = []
  if (filters.q) parts.push(filters.q)
  const roles = asList(filters.roles).map(slug => labelFor(facets.roles, slug) || roleLabel(slug))
  if (roles.length) parts.push(roles.join(', '))
  const locations = asList(filters.loc).map(slug => labelFor(FILTER_FALLBACK.locations, slug))
  if (locations.length) parts.push(locations.join(', '))
  const levels = asList(filters.lvl).map(slug => labelFor(FILTER_FALLBACK.levels, slug))
  if (levels.length) parts.push(levels.join(', '))
  const industries = asList(filters.ind).map(slug => labelFor(facets.industries, slug))
  if (industries.length) parts.push(industries.join(', '))
  const workplaces = asList(filters.sch).map(slug => labelFor(FILTER_FALLBACK.workplaces, slug))
  if (workplaces.length) parts.push(workplaces.join(', '))
  const types = asList(filters.types).map(slug => labelFor(FILTER_FALLBACK.types, slug))
  if (types.length) parts.push(types.join(', '))
  return parts.join(' · ')
}

function activeCount(filters: RecommendationFilters): number {
  let n = 0
  for (const key of LIST_KEYS) if (filters[key]?.length) n++
  if (filters.q?.trim()) n++
  return n
}

export function CoachFilters({
  facets,
  applied,
  busy,
  onApply,
}: {
  facets: JobFacets
  applied: RecommendationFilters
  busy: boolean
  onApply: (filters: RecommendationFilters) => void
}) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState<Draft>(() => toDraft(applied))
  const appliedKey = canonical(applied)

  // A refresh returns the saved scope; that is the truth, so reset the draft.
  useEffect(() => {
    setDraft(toDraft(applied))
  }, [appliedKey]) // eslint-disable-line react-hooks/exhaustive-deps

  const patch = (next: Partial<Draft>) => setDraft({ ...draft, ...next })
  const changed = canonical(toFilters(draft)) !== appliedKey
  const count = activeCount(applied)
  const summary = summarize(applied, facets)

  const locations = facets.locations.length ? facets.locations : FILTER_FALLBACK.locations
  const levels = facets.levels.length ? facets.levels : FILTER_FALLBACK.levels
  const workplaces = facets.workplaces.length ? facets.workplaces : FILTER_FALLBACK.workplaces
  const types = facets.types.length ? facets.types : FILTER_FALLBACK.types

  const toggleType = (slug: string) =>
    patch({
      types: draft.types.includes(slug)
        ? draft.types.filter(t => t !== slug)
        : [...draft.types, slug],
    })

  const submit = () => {
    onApply(toFilters(draft))
    setOpen(false)
  }

  return (
    <div className="filterbar">
      <div className="filterbar-row">
        <button
          type="button"
          className="searchtrigger"
          aria-expanded={open}
          onClick={() => setOpen(v => !v)}
        >
          <span className="stic"><Icon n="set" /></span>
          <span className={'sttext' + (summary ? ' on' : '')}>
            {summary || 'All open jobs — the coach searches everything'}
          </span>
          <span className="stfilters">
            <span>Scope</span>
            {count > 0 && <span className="badge">{count}</span>}
            <span className={'caret' + (open ? ' up' : '')} aria-hidden="true">⌄</span>
          </span>
        </button>
      </div>

      {/* Kept mounted so the draft survives closing and reopening. */}
      <div className={'panel filters' + (open ? ' filters-open' : '')} hidden={!open}>
        <div className="fgrid">
          <div className="spanall">
            <Picker
              id="coach-roles"
              label="Target roles"
              placeholder="All roles"
              options={facets.roles}
              noun="role"
              value={draft.roles}
              onChange={roles => patch({ roles })}
              labelOf={slug => labelFor(facets.roles, slug) || roleLabel(slug)}
            />
          </div>

          <div>
            <label htmlFor="coach-q">Keywords</label>
            <input
              id="coach-q"
              className="f"
              type="search"
              value={draft.q}
              placeholder="e.g. React, fintech, growth"
              onChange={e => patch({ q: e.target.value })}
              onKeyDown={e => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  submit()
                }
              }}
            />
          </div>

          <Picker
            id="coach-loc"
            label="Location"
            placeholder="All locations"
            options={locations}
            noun="location"
            value={draft.loc}
            onChange={loc => patch({ loc })}
          />

          <Picker
            id="coach-lvl"
            label="Experience Level"
            placeholder="Any level"
            options={levels}
            noun="level"
            value={draft.lvl}
            onChange={lvl => patch({ lvl })}
          />

          <Picker
            id="coach-ind"
            label="Company / Industry"
            placeholder="All industries"
            options={facets.industries}
            noun="industry"
            value={draft.ind}
            onChange={ind => patch({ ind })}
          />

          <Picker
            id="coach-sch"
            label="Workplace"
            placeholder="Remote, hybrid, on-site"
            options={workplaces}
            noun="workplace"
            value={draft.sch}
            onChange={sch => patch({ sch })}
          />

          <div>
            <label>Job Type</label>
            <div className="chips">
              {types.map(t => (
                <button
                  key={t.slug}
                  type="button"
                  className="chip"
                  aria-pressed={draft.types.includes(t.slug)}
                  onClick={() => toggleType(t.slug)}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>

          <div className="filterapply">
            <span className="fhint">
              {changed
                ? `${count === 0 ? 'New scope' : 'Scope changed'} — applying regenerates your matches.`
                : 'The coach only considers jobs inside this scope.'}
            </span>
            <span className="factions">
              <button
                type="button"
                className="linkbtn"
                onClick={() => setDraft(toDraft({}))}
                disabled={busy}
              >
                Clear
              </button>
              <button
                type="button"
                className="btn"
                onClick={submit}
                disabled={!changed || busy}
              >
                {busy ? 'Regenerating…' : changed ? 'Apply and regenerate' : 'Scope applied'}
              </button>
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
