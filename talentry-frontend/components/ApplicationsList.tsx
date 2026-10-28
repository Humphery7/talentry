'use client'
import Link from 'next/link'
import { useCallback, useEffect, useState } from 'react'
import { loadSession } from '@/lib/auth'
import { ApiError, call, STATUS_TEXT, type Row, type Status } from '@/lib/applications'

const GROUPS: [string, Status[]][] = [
  ['Needs your attention', ['needs_input', 'pending_approval', 'unconfirmed']],
  ['In progress', ['queued', 'in_progress', 'approved', 'submitting']],
  ['Done', ['submitted']],
  ['Problems', ['failed', 'cancelled']],
]

export default function ApplicationsList() {
  const [rows, setRows] = useState<Row[] | null>(null)
  const [msg, setMsg] = useState('')
  const [authed, setAuthed] = useState(true)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    if (!loadSession()) { setAuthed(false); return }
    try { setRows(await call<Row[]>('')) } catch { /* keep the last list */ }
  }, [])

  useEffect(() => {
    void load()
    const timer = setInterval(load, 8000)
    return () => clearInterval(timer)
  }, [load])

  async function queueTop() {
    setBusy(true)
    setMsg('Looking at your best matches…')
    try {
      const result = await call<{ queued: number }>('/queue-top', 'POST', { limit: 5 })
      setMsg(result.queued
        ? `Queued ${result.queued} recommended job(s). Nothing is submitted until you approve it.`
        : 'No new recommended jobs to queue. Generate recommendations in Career Coach first.')
      await load()
    } catch (error) {
      setMsg(error instanceof ApiError ? error.messages.join(' ') : 'Could not queue jobs.')
    } finally {
      setBusy(false)
    }
  }

  if (!authed) {
    return <div className="panel"><Link href="/?auth=login" style={{ textDecoration: 'underline' }}>Log in</Link> to see your applications.</div>
  }
  if (!rows) return <div className="panel">Loading applications…</div>

  return (
    <div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center', justifyContent: 'space-between', margin: '8px 0 24px' }}>
        <h2 style={{ fontSize: 30 }}>Applications</h2>
        <button className="btn" style={{ width: 'auto', padding: '0 24px' }} disabled={busy} onClick={() => void queueTop()}>
          {busy ? 'Queueing…' : 'Queue my top matches'}
        </button>
      </div>
      {msg && <p className="m" role="status" style={{ marginBottom: 16 }}>{msg}</p>}
      {rows.length === 0 && <div className="panel empty"><b>No applications yet</b>Open a job and choose “Apply with Talentry”.</div>}
      {GROUPS.map(([title, statuses]) => {
        const list = rows.filter(row => statuses.includes(row.status))
        if (!list.length) return null
        return (
          <section key={title} style={{ marginBottom: 28 }}>
            <h3 style={{ fontSize: 16, margin: '0 0 12px' }}>{title}</h3>
            <div style={{ display: 'grid', gap: 12 }}>
              {list.map(row => (
                <Link key={row.id} href={`/applications/${row.id}`} className="panel" style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'center', textDecoration: 'none', padding: '18px 24px' }}>
                  <span>
                    <b>{row.jobTitle ?? 'Application'}</b><br />
                    <span className="m">{row.company ?? ''}</span>
                  </span>
                  <span style={{ textAlign: 'right' }}>
                    <span className="chip">
                      {STATUS_TEXT[row.status][0]}
                      {row.status === 'needs_input' && row.attentionCount ? ` · ${row.attentionCount}` : ''}
                    </span>
                    {row.error && <div className="m" style={{ marginTop: 6, maxWidth: 320 }}>{row.error}</div>}
                  </span>
                </Link>
              ))}
            </div>
          </section>
        )
      })}
    </div>
  )
}
