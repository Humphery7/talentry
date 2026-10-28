'use client'
import { useRouter } from 'next/navigation'
import { useState } from 'react'
import { authHeaders, loadSession } from '@/lib/auth'
export default function ApplyButton({ jobId }: { jobId: number }) {
  const router = useRouter()
  const [s, setS] = useState<'idle' | 'busy' | 'done' | 'err'>('idle')
  async function apply() {
    if (!loadSession()) return router.push('/?auth=login')
    setS('busy')
    try {
      const r = await fetch(`${process.env.NEXT_PUBLIC_API_URL ?? ''}/api/applications`, { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify({ jobId }) })
      setS(r.ok ? 'done' : 'err')
    } catch { setS('err') }
  }
  return <button className="btn" disabled={s === 'busy' || s === 'done'} onClick={apply}>{{ idle: 'Mark as applied', busy: 'Saving…', done: 'Application saved', err: 'Failed, try again' }[s]}</button>
}
