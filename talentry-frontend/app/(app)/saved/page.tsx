'use client'
import { useEffect, useState } from 'react'
import type { Job } from '@/lib/data'
import { useSaved } from '@/lib/useSaved'
import JobCard from '@/components/JobCard'
const cache = new Map<number, Job>() // module-level: revisiting the page is instant
export default function Saved() {
  const { ids, ready } = useSaved(), [, bump] = useState(0), key = ids.join(',')
  useEffect(() => {
    const missing = ids.filter(i => !cache.has(i))
    if (!missing.length) return
    const c = new AbortController()
    fetch(`${process.env.NEXT_PUBLIC_API_URL ?? ''}/api/jobs?ids=${missing.join(',')}`, { signal: c.signal })
      .then(r => r.json()).then((d: { data: Job[] }) => { d.data.forEach(j => cache.set(j.id, j)); bump(n => n + 1) }).catch(() => {})
    return () => c.abort()
  }, [key]) // eslint-disable-line react-hooks/exhaustive-deps
  const shown = ids.map(i => cache.get(i)).filter(Boolean) as Job[]
  const waiting = !ready ? 3 : ids.length - shown.length
  return (
    <>
      <h1>Saved jobs</h1>
      <div className="stats"><span>{ready ? `${ids.length} saved` : ' '}</span></div>
      <div className="grid" style={{ marginTop: 34 }}>
        {ready && !ids.length ? <div className="empty"><b>Nothing saved yet</b>Tap the bookmark on a job to keep it here.</div> : shown.map((j, i) => <JobCard key={j.id} job={j} i={i} />)}
        {Array.from({ length: waiting }, (_, i) => <div key={'s' + i} className="sk" />)}
      </div>
    </>
  )
}
