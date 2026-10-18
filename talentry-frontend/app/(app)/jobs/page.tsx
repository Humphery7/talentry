import type { Metadata } from 'next'
import Link from 'next/link'
import { getJobs } from '@/lib/api'
import { parseQuery } from '@/lib/data'
import JobCard from '@/components/JobCard'
import { AIPanel, SearchBar, SidePanel } from '@/components/Filters'
export const metadata: Metadata = { title: 'Find Jobs' }
export default async function Jobs({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const sp = await searchParams, q = parseQuery(sp)
  const { jobs, total, pages } = await getJobs(q)
  const page = q.page ?? 1
  // Same filters, different page.
  const pageHref = (p: number) => {
    const params = new URLSearchParams()
    for (const [k, v] of Object.entries(sp)) if (v !== undefined) params.set(k, Array.isArray(v) ? v[0] ?? '' : v)
    params.set('page', String(p))
    return `/jobs?${params}`
  }
  return (
    <>
      <h1>Welcome back</h1>
      <div className="stats"><span>{total} job match{total === 1 ? '' : 'es'} found{total > jobs.length ? ` (page ${page} of ${pages})` : ' for you today'}</span><span>CV Score: 87/100</span><span>Interview Preparedness: 62%</span></div>
      <SearchBar />
      <div className="main">
        <aside className="side"><AIPanel /><SidePanel /></aside>
        <main className="grid" id="results" aria-live="polite">
          {jobs.length ? jobs.map((j, i) => <JobCard key={j.id} job={j} i={i} />) : <div className="empty"><b>No jobs match these filters</b>Widen the salary range or clear a filter.</div>}
        </main>
      </div>
      {pages > 1 && <nav className="pager" aria-label="Pages" style={{ display: 'flex', gap: 12, marginTop: 24 }}>
        {page > 1 ? <Link className="btn" href={pageHref(page - 1)}>← Prev</Link> : null}
        {page < pages ? <Link className="btn" href={pageHref(page + 1)}>Next →</Link> : null}
      </nav>}
    </>
  )
}
