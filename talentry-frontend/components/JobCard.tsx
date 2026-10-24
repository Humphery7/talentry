'use client'
import Link from 'next/link'
import { memo, type CSSProperties } from 'react'
import type { Job } from '@/lib/data'
import { useSaved } from '@/lib/useSaved'
import { CompanyLogo, Icon, Verified } from './ui'
export default memo(function JobCard({ job, i }: { job: Job; i: number }) {
  const { ids, toggle } = useSaved()
  return (
    <article className="job" style={{ '--i': Math.min(i, 12) } as CSSProperties}>
      <div className="row"><CompanyLogo job={job} /><span className="date">{job.date}</span>
        <button className="bm" aria-pressed={ids.includes(job.id)} aria-label={`Save ${job.title}`} onClick={() => toggle(job.id)}><Icon n="bm" /></button></div>
      <div className="co">{job.co}<Verified /></div>
      <h3>{job.title}</h3>
      <div className="tags">{job.tags.map(t => <span key={t}>{t}</span>)}</div>
      <div className="sal2">{job.min || job.max ? `$${job.min}K - $${job.max}K` : 'Salary not listed'}</div>
      <div className="foot"><span>{job.loc}</span><Link className="det" href={`/jobs/${job.id}`}>Details</Link></div>
    </article>
  )
})
