'use client'
import Link from 'next/link'
import { useCallback, useEffect, useState } from 'react'
import { loadSession } from '@/lib/auth'
import { ApiError, call, STATUS_TEXT, WORKING, type Detail, type Field } from '@/lib/applications'

const SOURCE: Record<string, string> = {
  profile: 'From your profile',
  draft: 'AI draft, please check',
  user: 'Your answer',
  user_edit: 'Edited by you',
  saved: 'Your saved answer',
  document: 'Document',
  site: 'Pre-filled by the site',
  skip: 'Left blank',
}
const EDITABLE = ['needs_input', 'pending_approval', 'approved']

export default function ApplicationDetail({ id }: { id: string }) {
  const [data, setData] = useState<Detail | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    if (!loadSession()) { setError('Log in to see this application.'); return }
    try {
      setData(await call<Detail>(`/${id}`))
      setError('')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not load.')
    }
  }, [id])

  useEffect(() => { void load() }, [load])
  useEffect(() => {
    if (!data || !WORKING.includes(data.status)) return
    const timer = setInterval(load, 4000)
    return () => clearInterval(timer)
  }, [data, load])

  async function act(path: string, method = 'POST', body?: unknown, confirmText?: string) {
    if (confirmText && !window.confirm(confirmText)) return false
    setBusy(true)
    setError('')
    try {
      await call(`/${id}${path}`, method, body)
      await load()
      return true
    } catch (err) {
      setError(err instanceof ApiError ? err.messages.join(' ') : 'Something went wrong.')
      return false
    } finally {
      setBusy(false)
    }
  }

  if (!data) return <div className="panel">{error || 'Loading…'}</div>

  const [label, hint] = STATUS_TEXT[data.status]
  const open = data.attention.filter(item => item.answer === null)
  const questions = open.filter(item => item.kind === 'question')
  const manual = open.filter(item => item.kind === 'manual')
  const filled = data.fields.filter(field => field.status !== 'skipped')
  const blank = data.fields.filter(field => field.status === 'skipped')
  const editable = EDITABLE.includes(data.status)
  const employerUrl = data.applyUrl
  const coverLetter = data.documents.cover_letter

  return (
    <div>
      <Link href="/applications" className="back">← All applications</Link>
      <div className="panel" style={{ marginTop: 20 }}>
        <h2 style={{ fontSize: 28 }}>{data.jobTitle ?? 'Application'}</h2>
        <span className="m">
          {data.company ?? ''} · <Link href={`/jobs/${data.jobId}`} style={{ textDecoration: 'underline' }}>job posting</Link>
        </span>
        <p style={{ margin: '16px 0 0' }}>
          <span className="chip" aria-live="polite">{label}</span> <span className="m">{hint}</span>
        </p>
        {data.error && <p role="alert" className="m" style={{ marginTop: 10 }}>{data.error}</p>}
        {error && <p role="alert" style={{ marginTop: 10, color: 'var(--err, #c0392b)' }}>{error}</p>}
        {data.result?.confirmation && <p className="m" style={{ marginTop: 10 }}>Employer message: “{data.result.confirmation}”</p>}
        {data.result?.manual && <p className="m" style={{ marginTop: 10 }}>You submitted this yourself.</p>}
      </div>

      {questions.length > 0 && (
        <Questions
          items={questions}
          busy={busy}
          onSave={(answers) => act('/answers', 'POST', { answers })}
        />
      )}

      {manual.map(item => (
        <div key={item.id} className="panel" style={{ marginTop: 16 }}>
          <b>Action needed from you</b>
          <p style={{ margin: '8px 0' }}>{item.question}</p>
          {item.why && <p className="m">{item.why}</p>}
          <p className="m" style={{ margin: '8px 0 16px' }}>
            Talentry cannot complete this in its own browser. You can finish it on the employer’s site yourself, or retry once it is sorted.
          </p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
            {employerUrl && <a className="btn" style={{ width: 'auto', padding: '0 24px', textDecoration: 'none' }} href={employerUrl} target="_blank" rel="noreferrer">Open employer’s page</a>}
            <button className="btn" style={{ width: 'auto', padding: '0 24px' }} disabled={busy || questions.length > 0} onClick={() => void act('/resume')}>I’ve sorted it, retry</button>
            <button className="btn" style={{ width: 'auto', padding: '0 24px' }} disabled={busy} onClick={() => void act('/manual-complete', 'POST', {}, 'Mark this as submitted? Only do this if you really submitted it yourself.')}>I submitted it myself</button>
          </div>
        </div>
      ))}

      {data.warnings.length > 0 && (
        <div className="panel" role="status" style={{ marginTop: 16 }}>
          <b>Please check</b>
          {data.warnings.map(warning => <p key={warning} className="m" style={{ marginTop: 6 }}>{warning}</p>)}
        </div>
      )}

      {filled.length > 0 && (
        <div className="panel" style={{ marginTop: 16 }}>
          <b>Application answers</b>
          <div style={{ display: 'grid', gap: 14, marginTop: 14 }}>
            {filled.map(field => (
              <FieldRow
                key={field.key}
                field={field}
                disabled={!editable || busy}
                onSave={(value) => act('/fields', 'PUT', { key: field.key, value })}
              />
            ))}
          </div>
          {blank.length > 0 && (
            <p className="m" style={{ marginTop: 16 }}>
              Left blank: {blank.map(field => field.label).join(', ')}
              {blank.some(field => field.note) ? '. These were optional or needed your own answer.' : ''}
            </p>
          )}
        </div>
      )}

      {(data.documents.cv || coverLetter) && (
        <div style={{ display: 'grid', gap: 16, marginTop: 16 }}>
          {(['cv', 'cover_letter'] as const).map(kind => {
            const document = data.documents[kind]
            return document ? (
              <DocEditor
                key={`${kind}-${document.version}`}
                kind={kind}
                document={document}
                disabled={!editable || busy}
                onSave={(content) => act(`/documents/${kind}`, 'PUT', { content })}
                onRegenerate={() => act(`/documents/${kind}/regenerate`, 'POST', {}, 'Regenerate this document? Your edits to the current version are kept as a previous version.')}
              />
            ) : null
          })}
        </div>
      )}
      {!coverLetter && editable && (
        <button className="chip" style={{ marginTop: 12 }} disabled={busy} onClick={() => void act('/documents/cover_letter/regenerate')}>
          Add a cover letter
        </button>
      )}

      {data.screenshot && (
        <details className="panel" style={{ marginTop: 16 }}>
          <summary>Page as Talentry last saw it</summary>
          <img
            src={`data:image/jpeg;base64,${data.screenshot}`}
            alt="Screenshot of the employer's application form"
            style={{ width: '100%', marginTop: 12, borderRadius: 12 }}
          />
        </details>
      )}

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginTop: 24 }}>
        {data.status === 'pending_approval' && (
          <button className="btn" style={{ width: 'auto', padding: '0 28px' }} disabled={busy}
            onClick={() => void act('/approve', 'POST', {}, `Submit this application to ${data.company ?? 'the employer'}? They will receive exactly what is shown here. This cannot be undone.`)}>
            Approve &amp; submit
          </button>
        )}
        {['failed', 'cancelled'].includes(data.status) && (
          <button className="btn" style={{ width: 'auto', padding: '0 28px' }} disabled={busy} onClick={() => void act('/retry')}>Try again</button>
        )}
        {data.status === 'unconfirmed' && (
          <>
            <button className="btn" style={{ width: 'auto', padding: '0 28px' }} disabled={busy} onClick={() => void act('/manual-complete', 'POST', {}, 'Mark as submitted? Only if you checked it went through.')}>It went through</button>
            <button className="btn" style={{ width: 'auto', padding: '0 28px' }} disabled={busy}
              onClick={() => void act('/retry', 'POST', { confirmNotSubmitted: true }, 'Confirm you checked your email and the employer site and the application was NOT submitted?')}>
              It didn’t, try again
            </button>
          </>
        )}
        {['queued', 'in_progress', 'needs_input', 'pending_approval', 'approved'].includes(data.status) && (
          <button className="chip" disabled={busy} onClick={() => void act('/cancel', 'POST', {}, 'Cancel this application?')}>Cancel</button>
        )}
      </div>

      <details className="panel" style={{ marginTop: 24 }}>
        <summary>Activity</summary>
        <ul style={{ listStyle: 'none', marginTop: 12, display: 'grid', gap: 6 }}>
          {data.events.map((event, index) => (
            <li key={`${event.createdAt}-${index}`} className="m">
              {new Date(event.createdAt).toLocaleString()} — {event.message}
            </li>
          ))}
        </ul>
      </details>
    </div>
  )
}

function Questions({ items, busy, onSave }: { items: Detail['attention']; busy: boolean; onSave: (answers: { id: string; answer: string }[]) => void }) {
  const [values, setValues] = useState<Record<string, string>>({})
  const ready = items.every(item => (values[item.id] ?? '').trim())
  return (
    <div className="panel" style={{ marginTop: 16 }}>
      <b>Talentry needs your answers to continue</b>
      <p className="m" style={{ margin: '6px 0 16px' }}>
        Talentry never guesses sensitive or personal answers. Your answers are saved so you are not asked the same thing twice.
      </p>
      <div style={{ display: 'grid', gap: 16 }}>
        {items.map(item => (
          <label key={item.id} style={{ display: 'grid', gap: 6 }}>
            <span>
              <b>{item.question}</b>
              {item.sensitive && <span className="chip" style={{ marginLeft: 8 }}>sensitive</span>}
            </span>
            {item.why && <span className="m">{item.why}</span>}
            {item.options?.length ? (
              <select className="f" value={values[item.id] ?? ''} onChange={event => setValues({ ...values, [item.id]: event.target.value })}>
                <option value="">Choose…</option>
                {item.options.map(option => <option key={option}>{option}</option>)}
              </select>
            ) : (
              <input className="f" value={values[item.id] ?? ''} onChange={event => setValues({ ...values, [item.id]: event.target.value })} />
            )}
          </label>
        ))}
      </div>
      <button className="btn" style={{ width: 'auto', padding: '0 28px', marginTop: 20 }} disabled={busy || !ready}
        onClick={() => onSave(items.map(item => ({ id: item.id, answer: (values[item.id] ?? '').trim() })))}>
        Save and continue
      </button>
    </div>
  )
}

function FieldRow({ field, disabled, onSave }: { field: Field; disabled: boolean; onSave: (value: string) => void }) {
  const [value, setValue] = useState(field.value)
  useEffect(() => setValue(field.value), [field.value])
  const long = field.kind === 'textarea'
  const fixed = field.kind === 'file'
  const commit = () => { if (value !== field.value) onSave(value) }
  return (
    <label style={{ display: 'grid', gap: 6 }}>
      <span>
        {field.label}{field.required && ' *'}{' '}
        <span className={field.status === 'draft' ? 'chip' : 'm'} style={field.status === 'draft' ? { marginLeft: 6 } : undefined}>
          {SOURCE[field.source] ?? field.source}
        </span>
      </span>
      {fixed ? <span className="m">{field.value} (edit below)</span>
        : field.options?.length ? (
          <select className="f" value={value} disabled={disabled} onChange={event => { setValue(event.target.value); onSave(event.target.value) }}>
            {!field.required && <option value="">—</option>}
            {field.options.map(option => <option key={option}>{option}</option>)}
          </select>
        ) : long ? (
          <textarea className="f" style={{ height: 140 }} value={value} disabled={disabled} onChange={event => setValue(event.target.value)} onBlur={commit} />
        ) : field.kind === 'checkbox' ? (
          <span className="m">{field.value === 'yes' ? 'Ticked' : 'Not ticked'}</span>
        ) : (
          <input className="f" value={value} disabled={disabled} onChange={event => setValue(event.target.value)} onBlur={commit} />
        )}
      {field.note && <span className="m">{field.note}</span>}
    </label>
  )
}

function DocEditor({ kind, document, disabled, onSave, onRegenerate }: {
  kind: 'cv' | 'cover_letter'
  document: NonNullable<Detail['documents']['cv']>
  disabled: boolean
  onSave: (content: string) => void
  onRegenerate: () => void
}) {
  const [text, setText] = useState(document.content)
  const name = kind === 'cv' ? 'Tailored CV' : 'Cover letter'
  return (
    <div className="panel">
      <b>{name}</b> <span className="m">version {document.version} · {document.origin === 'original' ? 'your original CV' : document.origin.replace(/_/g, ' ')}</span>
      {document.notes.map(note => <p key={note} className="m" style={{ marginTop: 6 }}>{note}</p>)}
      <textarea className="f" style={{ height: 320, fontFamily: 'inherit' }} value={text} disabled={disabled} onChange={event => setText(event.target.value)} aria-label={`${name} text`} />
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <button className="chip" disabled={disabled || text === document.content || !text.trim()} onClick={() => onSave(text)}>Save as new version</button>
        <button className="chip" disabled={disabled} onClick={onRegenerate}>Regenerate</button>
      </div>
      <p className="m" style={{ marginTop: 10 }}>The approved version is the one that gets uploaded. Earlier versions are kept ({document.versions.length} so far).</p>
    </div>
  )
}
