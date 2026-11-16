'use client'

import Link from 'next/link'
import { useEffect, useState, type FormEvent } from 'react'
import {
  getAiKeyStatus,
  removeAiKey,
  saveAiKey,
  type AiKeyStatus,
} from '@/lib/ai-settings'

function message(err: unknown): string {
  return err instanceof Error ? err.message : 'Something went wrong. Try again.'
}

export default function AiSettings() {
  const [status, setStatus] = useState<AiKeyStatus | null>(null)
  const [key, setKey] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  useEffect(() => {
    let alive = true
    void getAiKeyStatus()
      .then((value) => {
        if (alive) setStatus(value)
      })
      .catch((err) => {
        if (alive) setError(message(err))
      })
      .finally(() => {
        if (alive) setLoading(false)
      })
    return () => {
      alive = false
    }
  }, [])

  async function save(event: FormEvent) {
    event.preventDefault()
    const value = key.trim()
    if (!value || busy) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      setStatus(await saveAiKey(value))
      // Never keep the plaintext in the browser after it has been saved.
      setKey('')
      setNotice('Your Gemini key is saved. AI features will use it from now on.')
    } catch (err) {
      setError(message(err))
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    if (busy) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      setStatus(await removeAiKey())
      setNotice('Your Gemini key was removed. AI features are paused until you add one again.')
    } catch (err) {
      setError(message(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="panel" style={{ maxWidth: 640 }}>
      <h2 style={{ marginTop: 0 }}>Gemini API key</h2>
      <p className="m" style={{ marginTop: 0 }}>
        Talentry uses Gemini for job recommendations, interview prep, CV tailoring and
        auto-apply. Each account uses its own key, so your usage stays on your Google
        account. The key is stored encrypted and never shown again after saving.
      </p>

      {loading ? (
        <p className="m">Checking your key…</p>
      ) : status?.configured ? (
        <div style={{ margin: '18px 0' }}>
          <p style={{ margin: '0 0 6px' }}>
            <b>Key saved</b> <span className="m">({status.hint})</span>
          </p>
          <p className="m" style={{ margin: '0 0 12px' }}>
            Saved {status.updatedAt ? new Date(status.updatedAt).toLocaleString() : 'recently'}.
            Paste a new key below to replace it.
          </p>
          <button
            type="button"
            className="btn"
            style={{ width: 'auto', padding: '0 20px', background: 'transparent', color: 'inherit', border: '1px solid var(--line)' }}
            disabled={busy}
            onClick={remove}
          >
            Remove key
          </button>
        </div>
      ) : (
        <p className="m" style={{ margin: '18px 0' }}>
          <b>No key saved.</b> AI features will ask you for one until you add it here.
        </p>
      )}

      <form onSubmit={save} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <label htmlFor="gemini-key" style={{ fontWeight: 600 }}>
          {status?.configured ? 'Replace key' : 'Add your key'}
        </label>
        <input
          id="gemini-key"
          className="f"
          type="password"
          value={key}
          onChange={(event) => setKey(event.target.value)}
          placeholder="Paste your Gemini API key"
          autoComplete="off"
          spellCheck={false}
          disabled={busy}
        />
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <button
            className="btn"
            type="submit"
            style={{ width: 'auto', padding: '0 24px' }}
            disabled={busy || !key.trim()}
          >
            {busy ? 'Checking…' : 'Save key'}
          </button>
          <a
            className="m"
            href="https://aistudio.google.com/apikey"
            target="_blank"
            rel="noreferrer"
          >
            Get a free Gemini key
          </a>
        </div>
      </form>

      {error ? <p className="perr" role="alert" style={{ marginTop: 14 }}>{error}</p> : null}
      {notice ? <p className="m" role="status" style={{ marginTop: 14 }}>{notice}</p> : null}

      <p className="m" style={{ marginBottom: 0, marginTop: 18 }}>
        Your key is only used for your own requests. If you remove it, anything that
        needs Gemini pauses. You can add it again at any time. See{' '}
        <Link href="/applications">your applications</Link> to retry a stopped one.
      </p>
    </div>
  )
}
