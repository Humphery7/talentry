import type { Metadata } from 'next'
import Link from 'next/link'
import { getJobs, getJobFacets } from '@/lib/api'
import { parseQuery, groupJobsByCompany } from '@/lib/data'
import CompanyJobGroup from '@/components/CompanyJobGroup'
import { FilterPanel } from '@/components/Filters'

export const metadata: Metadata = { title: 'Find Jobs' }

export default async function Jobs({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  const sp     = await searchParams
  const q      = parseQuery(sp)
  const page   = q.page ?? 1

  const [{ jobs, total, pages }, facets] = await Promise.all([
    getJobs(q),
    getJobFacets(),
  ])

  /* Group the flat job list by company for the card-per-company layout. */
  const groups = groupJobsByCompany(jobs)

  /** Same filters, different page number. */
  const pageHref = (p: number) => {
    const params = new URLSearchParams()
    for (const [k, v] of Object.entries(sp)) {
      if (v !== undefined) params.set(k, Array.isArray(v) ? v[0] ?? '' : v)
    }
    params.set('page', String(p))
    return `/jobs?${params}`
  }

  /** Same filters, different ordering. `undefined` restores the default. */
  const sortHref = (sort?: string) => {
    const params = new URLSearchParams()
    for (const [k, v] of Object.entries(sp)) {
      if (k === 'page' || k === 'sort' || v === undefined) continue
      params.set(k, Array.isArray(v) ? v[0] ?? '' : v)
    }
    if (sort) params.set('sort', sort)
    const query = params.toString()
    return query ? `/jobs?${query}` : '/jobs'
  }
  const ordering = q.sort === 'recent' ? 'recent' : 'newest'

  return (
    <>
      <h1>Find your next role</h1>

      <div className="stats">
        <span>
          {total} open role{total === 1 ? '' : 's'} found
          {total > jobs.length ? ` · page ${page} of ${pages}` : ''}
        </span>
        <span className="sortpick" aria-label="Sort jobs">
          <Link href={sortHref()} aria-current={ordering === 'newest' ? 'true' : undefined}>
            Newest
          </Link>
          <Link
            href={sortHref('recent')}
            aria-current={ordering === 'recent' ? 'true' : undefined}
            title="Jobs the crawler confirmed most recently, regardless of posting date"
          >
            Recently confirmed
          </Link>
        </span>
      </div>

      <FilterPanel facets={facets} />

      {/* Company-grouped results */}
      <main className="company-list" id="results" aria-live="polite">
        {groups.length ? (
          groups.map((g, i) => (
            <CompanyJobGroup key={g.name} group={g} index={i} />
          ))
        ) : (
          <div className="empty">
            <b>No jobs match these filters</b>
            Widen the salary range or clear a filter.
          </div>
        )}
      </main>

      {/* Pagination */}
      {pages > 1 && (
        <nav className="pager" aria-label="Pages">
          {page > 1 && (
            <Link className="btn pager-btn" href={pageHref(page - 1)}>
              ← Prev
            </Link>
          )}
          {page < pages && (
            <Link className="btn pager-btn" href={pageHref(page + 1)}>
              Next →
            </Link>
          )}
        </nav>
      )}
    </>
  )
}
