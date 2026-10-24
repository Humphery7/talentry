'use client'

import Link from 'next/link'
import { memo, type CSSProperties } from 'react'
import type { CompanyGroup } from '@/lib/data'
import { useSaved } from '@/lib/useSaved'
import { CompanyLogo, Icon, Verified } from './ui'

/* ────────────────────────────────────────────────────────
 * CompanyJobGroup
 *
 * Renders a single company card with:
 *   – a header showing logo, name, and open-role count
 *   – a list of job rows (title · location · date · bookmark)
 *
 * Used on the main /jobs page to group results by employer.
 * ──────────────────────────────────────────────────────── */

export default memo(function CompanyJobGroup({
  group,
  index,
}: {
  group: CompanyGroup
  index: number
}) {
  const { ids, toggle } = useSaved()
  const jobCount = group.jobs.length

  return (
    <section
      className="cg"
      style={{ '--gi': Math.min(index, 10) } as CSSProperties}
    >
      {/* ── Company header ── */}
      <div className="cg-header">
        <CompanyLogo job={{ bg: group.bg, ch: group.ch }} />

        <div className="cg-info">
          <h2 className="cg-name">
            {group.name}
            <Verified />
          </h2>
          <span className="cg-meta">
            {jobCount} open role{jobCount !== 1 ? 's' : ''}
          </span>
        </div>
      </div>

      {/* ── Job rows ── */}
      <ul className="cg-jobs">
        {group.jobs.map((job) => (
          <li key={job.id} className="cg-row">
            <Link href={`/jobs/${job.id}`} className="cg-link">
              <span className="cg-dot" />
              <span className="cg-title">{job.title}</span>
              <span className="cg-loc">{job.loc}</span>
              <span className="cg-date">{job.date}</span>
            </Link>

            <button
              className="cg-bm"
              aria-pressed={ids.includes(job.id)}
              aria-label={`Save ${job.title}`}
              onClick={() => toggle(job.id)}
            >
              <Icon n="bm" />
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
})
