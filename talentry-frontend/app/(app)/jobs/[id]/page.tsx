import Link from 'next/link'
import { notFound } from 'next/navigation'
import type { Metadata } from 'next'
import { getJob } from '@/lib/api'
import ApplyButton from '@/components/ApplyButton'
import { CompanyLogo } from '@/components/ui'
type P = { params: Promise<{ id: string }> }
export async function generateMetadata({ params }: P): Promise<Metadata> { const j = await getJob(+(await params).id); return { title: j ? `${j.title} at ${j.co}` : 'Job not found' } }
export default async function JobPage({ params }: P) {
  const job = await getJob(+(await params).id)
  if (!job) notFound()
  return (
    <div><Link href="/jobs" className="back">← Back to jobs</Link>
      <div className="panel" style={{ marginTop: 20, maxWidth: 640 }}>
        <CompanyLogo job={job} /><h2 style={{ fontSize: 30, margin: '16px 0 4px' }}>{job.title}</h2><span className="m">{job.co} · {job.loc}</span>
        <div className="dl"><div>Salary<b>{job.min || job.max ? `$${job.min}K – $${job.max}K` : 'Not listed'}</b></div><div>Posted<b>{job.date || '—'}</b></div><div>Applicants<b>{job.app}</b></div><div>Interviews<b>{job.int}</b></div></div>
        <div className="tags" style={{ marginBottom: 24 }}>{job.tags.map(t => <span key={t}>{t}</span>)}</div>
        <ApplyButton jobId={job.id} />
      </div>
    </div>
  )
}
