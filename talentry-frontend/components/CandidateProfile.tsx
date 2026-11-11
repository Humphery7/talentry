'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useId, useRef, useState, type FormEvent } from 'react'
import { authHeaders, loadSession, type Session } from '@/lib/auth'

export interface CandidateProfile {
  headline: string | null
  currentTitle: string | null
  yearsExperience: number | null
  location: string | null
  phone: string | null
  linkedinUrl: string | null
  githubUrl: string | null
  websiteUrl: string | null
  summary: string | null
  cvFilename?: string | null
  cvUpdatedAt?: string | null
}

type Draft = {
  headline: string
  currentTitle: string
  yearsExperience: string
  location: string
  phone: string
  linkedinUrl: string
  githubUrl: string
  websiteUrl: string
  summary: string
}

const EMPTY: Draft = {
  headline: '',
  currentTitle: '',
  yearsExperience: '',
  location: '',
  phone: '',
  linkedinUrl: '',
  githubUrl: '',
  websiteUrl: '',
  summary: '',
}

function toDraft(profile?: CandidateProfile | null): Draft {
  if (!profile) return EMPTY
  return {
    headline: profile.headline ?? '',
    currentTitle: profile.currentTitle ?? '',
    yearsExperience: profile.yearsExperience === null ? '' : String(profile.yearsExperience),
    location: profile.location ?? '',
    phone: profile.phone ?? '',
    linkedinUrl: profile.linkedinUrl ?? '',
    githubUrl: profile.githubUrl ?? '',
    websiteUrl: profile.websiteUrl ?? '',
    summary: profile.summary ?? '',
  }
}

const skipKey = (email: string) => `tl-profile-skip:${email}`
const PROFILE_EVENT = 'tl-profile'

/** Tells every mounted profile hook that the saved profile has changed. */
function announceProfile() {
  window.dispatchEvent(new Event(PROFILE_EVENT))
}

/** Loads the session and the candidate profile (null when the user has none). */
export function useCandidateProfile() {
  const [user, setUser] = useState<Session | null>(null)
  const [profile, setProfile] = useState<CandidateProfile | null | undefined>(undefined)

  useEffect(() => {
    const sync = () => setUser(loadSession())
    sync()
    window.addEventListener('tl-auth', sync)
    return () => window.removeEventListener('tl-auth', sync)
  }, [])

  useEffect(() => {
    if (!user) {
      setProfile(undefined)
      return
    }
    let alive = true
    const load = () => {
      fetch('/api/candidate-profile', { headers: authHeaders(), cache: 'no-store' })
        .then(r => (r.ok ? r.json() : null))
        .then(data => { if (alive) setProfile((data as CandidateProfile | null) ?? null) })
        .catch(() => { if (alive) setProfile(null) })
    }
    load()
    window.addEventListener(PROFILE_EVENT, load)
    return () => {
      alive = false
      window.removeEventListener(PROFILE_EVENT, load)
    }
  }, [user])

  return { user, profile, setProfile }
}

function ProfileForm({
  initial,
  onSaved,
  onSkip,
}: {
  initial?: CandidateProfile | null
  onSaved?: (profile: CandidateProfile) => void
  onSkip?: () => void
}) {
  const id = useId()
  const [draft, setDraft] = useState<Draft>(() => toDraft(initial))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)

  const field = (key: keyof Draft) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    setDraft(current => ({ ...current, [key]: e.target.value }))
    setSaved(false)
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      const r = await fetch('/api/candidate-profile', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({
          ...draft,
          yearsExperience: draft.yearsExperience === '' ? undefined : Number(draft.yearsExperience),
        }),
      })
      const data = await r.json().catch(() => null) as
        | (CandidateProfile & { message?: string | string[]; error?: string })
        | null
      if (!r.ok) {
        const reason = Array.isArray(data?.message) ? data.message.join(', ') : data?.message || data?.error
        throw new Error(reason || 'Could not save your profile.')
      }
      setSaved(true)
      if (data) onSaved?.(data)
      announceProfile()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save your profile.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="pform" onSubmit={submit}>
      <div className="prow">
        <div>
          <label htmlFor={`${id}-title`}>Current title</label>
          <input id={`${id}-title`} className="f" value={draft.currentTitle} onChange={field('currentTitle')} placeholder="e.g. Frontend Developer" />
        </div>
        <div>
          <label htmlFor={`${id}-years`}>Years of experience</label>
          <input id={`${id}-years`} className="f" type="number" min={0} max={80} value={draft.yearsExperience} onChange={field('yearsExperience')} placeholder="e.g. 3" />
        </div>
      </div>
      <div>
        <label htmlFor={`${id}-headline`}>Headline</label>
        <input id={`${id}-headline`} className="f" value={draft.headline} onChange={field('headline')} placeholder="e.g. Frontend engineer focused on accessible products" />
      </div>
      <div className="prow">
        <div>
          <label htmlFor={`${id}-location`}>Location</label>
          <input id={`${id}-location`} className="f" value={draft.location} onChange={field('location')} placeholder="e.g. Lagos, Nigeria (open to remote)" />
        </div>
        <div>
          <label htmlFor={`${id}-phone`}>Phone</label>
          <input id={`${id}-phone`} className="f" type="tel" value={draft.phone} onChange={field('phone')} placeholder="e.g. +234 801 234 5678" />
        </div>
      </div>
      <div className="prow">
        <div>
          <label htmlFor={`${id}-linkedin`}>LinkedIn</label>
          <input id={`${id}-linkedin`} className="f" inputMode="url" value={draft.linkedinUrl} onChange={field('linkedinUrl')} placeholder="linkedin.com/in/you" />
        </div>
        <div>
          <label htmlFor={`${id}-github`}>GitHub</label>
          <input id={`${id}-github`} className="f" inputMode="url" value={draft.githubUrl} onChange={field('githubUrl')} placeholder="github.com/you" />
        </div>
      </div>
      <div>
        <label htmlFor={`${id}-website`}>Website or portfolio</label>
        <input id={`${id}-website`} className="f" inputMode="url" value={draft.websiteUrl} onChange={field('websiteUrl')} placeholder="yoursite.com" />
      </div>
      <div>
        <label htmlFor={`${id}-summary`}>Summary</label>
        <textarea id={`${id}-summary`} className="f ptextarea" value={draft.summary} onChange={field('summary')} placeholder="A short paragraph about what you do and what you are looking for." />
      </div>
      {error && <p className="perr" role="alert">{error}</p>}
      <div className="pactions">
        <button className="btn psubmit" disabled={busy}>{busy ? 'Saving…' : 'Save profile'}</button>
        {onSkip && <button type="button" className="linkbtn" onClick={onSkip}>Skip for now</button>}
        {saved && <span className="psaved">Saved.</span>}
      </div>
    </form>
  )
}

function CvUpload({
  profile,
  onUploaded,
}: {
  profile: CandidateProfile | null
  onUploaded: (profile: CandidateProfile) => void
}) {
  const input = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function upload(file?: File) {
    if (!file) return
    setError('')
    if (file.size > 5 * 1024 * 1024) {
      setError('Please choose a file up to 5MB.')
      return
    }
    if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
      setError('Please choose a PDF file.')
      return
    }
    setBusy(true)
    try {
      const r = await fetch('/api/candidate-profile/cv', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/pdf',
          'X-Filename': encodeURIComponent(file.name),
          ...authHeaders(),
        },
        body: file,
      })
      const data = await r.json().catch(() => null) as
        | (CandidateProfile & { message?: string | string[]; error?: string })
        | null
      if (!r.ok) {
        const reason = Array.isArray(data?.message) ? data.message.join(', ') : data?.message || data?.error
        throw new Error(reason || 'Could not upload your CV.')
      }
      if (data) onUploaded(data)
      announceProfile()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not upload your CV.')
    } finally {
      setBusy(false)
      if (input.current) input.current.value = ''
    }
  }

  async function download() {
    setError('')
    try {
      const r = await fetch('/api/candidate-profile/cv', { headers: authHeaders(), cache: 'no-store' })
      if (!r.ok) throw new Error('Could not download your CV.')
      const url = URL.createObjectURL(await r.blob())
      const link = document.createElement('a')
      const name = (profile?.cvFilename ?? 'cv').replace(/\.[^.]+$/, '') || 'cv'
      link.href = url
      link.download = `${name}.txt`
      link.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not download your CV.')
    }
  }

  return (
    <div className="pcv">
      <div className="pcv-row">
        <span className="pcv-icon">CV</span>
        <div className="pcv-info">
          <b>{profile?.cvFilename ?? 'No CV uploaded'}</b>
          <span>{profile?.cvUpdatedAt
            ? `Updated ${new Date(profile.cvUpdatedAt).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}`
            : 'PDF, up to 5MB.'}</span>
        </div>
        <div className="pcv-actions">
          <button type="button" className="btn pcv-btn" disabled={busy} onClick={() => input.current?.click()}>
            {busy ? 'Uploading…' : profile?.cvFilename ? 'Replace CV' : 'Upload CV'}
          </button>
          {profile?.cvFilename && <button type="button" className="linkbtn" onClick={download}>Download text</button>}
        </div>
      </div>
      <input ref={input} type="file" hidden accept=".pdf" onChange={e => upload(e.target.files?.[0])} />
      {error && <p className="perr" role="alert">{error}</p>}
    </div>
  )
}

/** The editable profile on `/profile`. */
export function ProfileEditor() {
  const { user, profile, setProfile } = useCandidateProfile()
  if (!user) {
    return <p className="m">Log in to view and edit your profile. <Link href="/?auth=login">Log in</Link></p>
  }
  if (profile === undefined) return <p className="m">Loading…</p>
  return (
    <div className="pstack">
      <div className="panel"><CvUpload profile={profile} onUploaded={setProfile} /></div>
      <div className="panel"><ProfileForm initial={profile} onSaved={setProfile} /></div>
    </div>
  )
}

/**
 * Optional first-login prompt inside the app. It stays quiet once the user
 * saves or chooses "Skip for now" (remembered per account on this device).
 */
export function ProfilePrompt() {
  const path = usePathname()
  const { user, profile, setProfile } = useCandidateProfile()
  const dialog = useRef<HTMLDialogElement>(null)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (!user || path === '/profile') {
      setOpen(false)
      return
    }
    if (profile === undefined) return
    if (profile !== null) {
      setOpen(false)
      return
    }
    if (!localStorage.getItem(skipKey(user.email))) setOpen(true)
  }, [user, profile, path])

  useEffect(() => {
    const el = dialog.current
    if (!el) return
    if (open && !el.open) el.showModal()
    if (!open && el.open) el.close()
  }, [open])

  function skip() {
    if (user) localStorage.setItem(skipKey(user.email), '1')
    setOpen(false)
  }

  return (
    <dialog
      ref={dialog}
      className="profile-dlg"
      aria-labelledby="profile-title"
      onCancel={e => { e.preventDefault(); skip() }}
    >
      <h2 id="profile-title">Complete your profile</h2>
      <p>A few details help us match you with the right roles. This is optional — you can fill it in later from your account menu.</p>
      <ProfileForm
        initial={profile}
        onSaved={saved => {
          setProfile(saved)
          if (user) localStorage.removeItem(skipKey(user.email))
          setOpen(false)
        }}
        onSkip={skip}
      />
    </dialog>
  )
}
