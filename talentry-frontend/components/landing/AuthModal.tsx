'use client'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { saveSession } from '@/lib/auth'
import { Apple, Brand, Li } from './icons'

function Field({ icon, right, ...p }: { icon: 'mail' | 'lock' | 'user'; right?: ReactNode } & React.InputHTMLAttributes<HTMLInputElement>) {
  return <label className="fld"><Li n={icon} /><input {...p} aria-label={p.placeholder} />{right}</label>
}
function Form({ mode, onClose, next }: { mode: 'login' | 'signup'; onClose: () => void; next: string }) {
  const login = mode === 'login'
  const [f, setF] = useState({ name: '', email: '', password: '' }), [show, setShow] = useState(false), [err, setErr] = useState(''), [busy, setBusy] = useState(false)
  const up = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF(v => ({ ...v, [k]: e.target.value }))
  const nextParam = next !== '/jobs' ? '&next=' + encodeURIComponent(next) : ''
  async function submit(e: FormEvent) {
    e.preventDefault(); setErr('')
    if (!login && !f.name.trim()) return setErr('Enter your full name.')
    if (!/^\S+@\S+\.\S+$/.test(f.email)) return setErr('Enter a valid email address.')
    if (f.password.length < 8) return setErr('Password must be at least 8 characters.')
    setBusy(true)
    try {
      const r = await fetch(`${process.env.NEXT_PUBLIC_API_URL ?? ''}/api/auth/${mode}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(f) })
      const d = await r.json().catch(() => ({})) as { error?: string; message?: string | string[]; accessToken?: string; user?: { name: string; email: string } }
      if (!r.ok) throw new Error(d.error || (Array.isArray(d.message) ? d.message.join(', ') : d.message) || 'Something went wrong.')
      if (!d.accessToken || !d.user) throw new Error('Something went wrong.')
      saveSession({ token: d.accessToken, name: d.user.name, email: d.user.email })
      window.location.assign(next)
    } catch (x) { setErr(x instanceof Error ? x.message : 'Network error.'); setBusy(false) }
  }
  return (
    <div className="am">
      <button className="x" aria-label="Close" onClick={onClose}><Li n="x" /></button>
      <form className="af" onSubmit={submit} noValidate>
        <Brand />
        <h2>{login ? 'Welcome back' : 'Create your account'}</h2>
        <p className="sub">{login ? 'Log in to continue your journey.' : 'Join Talentry and get matched with jobs and scholarships that fit your goals.'}</p>
        {!login && <Field icon="user" placeholder="Full name" autoComplete="name" value={f.name} onChange={up('name')} />}
        <Field icon="mail" type="email" placeholder="Email address" autoComplete="email" value={f.email} onChange={up('email')} />
        <Field icon="lock" type={show ? 'text' : 'password'} placeholder="Password" autoComplete={login ? 'current-password' : 'new-password'} value={f.password} onChange={up('password')}
          right={<button type="button" aria-label={show ? 'Hide password' : 'Show password'} onClick={() => setShow(s => !s)}><Li n={show ? 'eyeoff' : 'eye'} /></button>} />
        <p className="err" role="alert">{err}</p>
        <button className="go" disabled={busy}>{busy ? 'Please wait…' : login ? 'Log in' : 'Create account'}</button>
        <div className="or">or continue with</div>
        <div className="sso">
          <button type="button" onClick={() => { window.location.href = `${process.env.NEXT_PUBLIC_API_URL ?? ''}/api/auth/google` }}><span className="g">G</span>Google</button>
          <button type="button" onClick={() => setErr('Apple sign-in is not connected yet.')}><Apple />Apple</button>
        </div>
        <p className="sw">{login ? "Don't have an account?" : 'Already have an account?'}
          <Link href={(login ? '/?auth=signup' : '/?auth=login') + nextParam} replace scroll={false}>{login ? 'Sign up' : 'Log in'}</Link></p>
      </form>
      <div className={'ap ' + mode} aria-hidden="true"><p>{login ? 'New opportunities await.' : 'Your goals matter here.'}</p><hr /></div>
    </div>
  )
}
export default function AuthModal() {
  const sp = useSearchParams(), router = useRouter(), m = sp.get('auth'), ref = useRef<HTMLDialogElement>(null)
  const requestedNext = sp.get('next')
  const next = requestedNext && requestedNext.startsWith('/') && !requestedNext.startsWith('//') ? requestedNext : '/jobs'
  const mode = m === 'login' || m === 'signup' ? m : null
  useEffect(() => {
    const d = ref.current; if (!d) return
    if (mode && !d.open) d.showModal(); if (!mode && d.open) d.close()
    document.documentElement.style.overflow = mode ? 'hidden' : ''
    return () => { document.documentElement.style.overflow = '' }
  }, [mode])
  const close = () => router.replace('/', { scroll: false })
  return <dialog ref={ref} className="lp-dlg" aria-label={mode === 'signup' ? 'Create your account' : 'Log in'} onClose={() => mode && close()} onClick={e => e.target === ref.current && close()}>{mode && <Form key={mode} mode={mode} onClose={close} next={next} />}</dialog>
}
