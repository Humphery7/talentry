'use client'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useState } from 'react'
import { loadSession } from '@/lib/auth'
import { ApiError, call, type Batch } from '@/lib/applications'

export default function AutoApplyButton({ jobId }: { jobId: number }) {
  const router = useRouter()
  const [busy, setBusy] = useState(false)
  const [problems, setProblems] = useState<string[]>([])

  async function go() {
    if (!loadSession()) { router.push('/?auth=login'); return }
    setBusy(true)
    setProblems([])
    try {
      await call<Batch>('', 'POST', { jobIds: [jobId] })
      router.push('/applications')
    } catch (error) {
      setProblems(error instanceof ApiError ? error.messages : ['Could not start. Try again.'])
      setBusy(false)
    }
  }

  return (
    <>
      <button className="btn" disabled={busy} onClick={() => void go()}>
        {busy ? 'Starting…' : 'Apply with Talentry'}
      </button>
      {problems.length > 0 && (
        <div role="alert" className="m" style={{ gridColumn: '1/-1' }}>
          {problems.map(problem => <div key={problem}>{problem}</div>)}
          <Link href="/profile" style={{ textDecoration: 'underline' }}>Open your profile</Link>
        </div>
      )}
    </>
  )
}
