import type { Metadata } from 'next'
import Link from 'next/link'
import { getJobs, getRoleFacets } from '@/lib/api'
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

  const [{ jobs, total, pages }, roles] = await Promise.all([
    getJobs(q),
    getRoleFacets(),
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

  return (
    <>
      <h1>Find your next role</h1>

      <div className="stats">
        <span>
          {total} open role{total === 1 ? '' : 's'} found
          {total > jobs.length ? ` · page ${page} of ${pages}` : ''}
        </span>
      </div>

      <FilterPanel roles={roles} />

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
