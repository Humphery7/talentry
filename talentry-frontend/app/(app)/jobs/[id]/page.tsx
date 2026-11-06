import Link from 'next/link'
import { notFound } from 'next/navigation'
import type { Metadata } from 'next'
import sanitizeHtml from 'sanitize-html'
import { getJob } from '@/lib/api'
import ApplyButton from '@/components/ApplyButton'
import AutoApplyButton from '@/components/AutoApplyButton'
import { CompanyLogo } from '@/components/ui'
type P = { params: Promise<{ id: string }> }

const DESCRIPTION_TAGS = [
  'p', 'br', 'hr', 'strong', 'b', 'em', 'i', 'u', 's',
  'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'blockquote', 'pre', 'code', 'a', 'img',
  'table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td',
  'span', 'div',
]

export async function generateMetadata({ params }: P): Promise<Metadata> { const j = await getJob(+(await params).id); return { title: j ? `${j.title} at ${j.co}` : 'Job not found' } }
export default async function JobPage({ params }: P) {
  const job = await getJob(+(await params).id)
  if (!job) notFound()
  const description = job.description
    ? sanitizeHtml(job.description, {
        allowedTags: DESCRIPTION_TAGS,
        allowedAttributes: {
          a: ['href', 'title', 'target', 'rel'],
          img: ['src', 'alt', 'title', 'width', 'height', 'loading'],
        },
        allowedSchemes: ['http', 'https', 'mailto'],
        transformTags: {
          a: sanitizeHtml.simpleTransform('a', { target: '_blank', rel: 'noopener noreferrer' }),
          img: sanitizeHtml.simpleTransform('img', { loading: 'lazy' }),
        },
      })
    : null
  return (
    <div><Link href="/jobs" className="back">← Back to jobs</Link>
      <div className="panel" style={{ marginTop: 20, maxWidth: 760 }}>
        <CompanyLogo job={job} /><h2 style={{ fontSize: 30, margin: '16px 0 4px' }}>{job.title}</h2><span className="m">{job.co} · {job.loc}</span>
        <div className="dl"><div>Salary<b>{job.min || job.max ? `$${job.min}K – $${job.max}K` : 'Not listed'}</b></div><div>Posted<b>{job.date || '—'}</b></div></div>
        <div className="tags" style={{ marginBottom: 16 }}>{job.tags.map(t => <span key={t}>{t}</span>)}</div>
        <h3 className="job-desc-title">Job description</h3>
        {description
          ? <div className="job-desc" dangerouslySetInnerHTML={{ __html: description }} />
          : <p className="m" style={{ marginBottom: 24 }}>No description provided.</p>}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
          <AutoApplyButton jobId={job.id} />
          <a href={job.url} target="_blank" rel="noreferrer" className="btn" style={{ textDecoration: 'none' }}>Apply on company site</a>
          <ApplyButton jobId={job.id} />
          <Link href={`/interview?jobId=${job.id}`} className="btn" style={{ textDecoration: 'none' }}>Interview prep</Link>
        </div>
      </div>
    </div>
  )
}
