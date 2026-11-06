'use client'
import { useEffect } from 'react'
import { usePathname } from 'next/navigation'
import { clearSession, loadSession, saveSession, type Session } from '@/lib/auth'

function safeNext(value: string | null) {
  return value && value.startsWith('/') && !value.startsWith('//') ? value : '/jobs'
}

// Checks a token with the backend and promotes it to the httpOnly route cookie.
async function promote(token: string, next: string, fallback?: Session) {
  const r = await fetch('/api/auth/session', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
  })
  const d = await r.json().catch(() => null) as { user?: { name?: string; email?: string } } | null
  if (!r.ok || !d?.user) throw new Error('session')
  saveSession({
    token,
    name: d.user.name ?? fallback?.name ?? '',
    email: d.user.email ?? fallback?.email ?? '',
  })
  window.history.replaceState(null, '', window.location.pathname + window.location.search)
  window.location.replace(next)
}

// After a Google login the backend redirects to /auth/callback with the JWT in
// the URL hash. This reads it once, exchanges it for an httpOnly session cookie,
// stores the browser session, then clears the hash and enters the app.
export default function AuthToken() {
  const pathname = usePathname()
  useEffect(() => {
    const hash = new URLSearchParams(window.location.hash.slice(1))
    const token = hash.get('token')
    const query = new URLSearchParams(window.location.search)
    const stored = loadSession()

    if (!token) {
      if (pathname === '/auth/callback') {
        window.location.replace('/?auth=login')
        return
      }
      // Existing localStorage sessions predate the cookie gate. If they were
      // bounced from a protected page, exchange the token and continue.
      if (pathname === '/' && query.has('next') && stored) {
        void promote(stored.token, safeNext(query.get('next')), stored).catch(() => clearSession())
      }
      return
    }

    void promote(token, '/jobs').catch(() => {
      clearSession()
      window.history.replaceState(null, '', window.location.pathname)
      window.location.replace('/?auth=login')
    })
  }, [pathname])
  return null
}
