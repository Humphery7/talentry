// Client-side session: JWT + user cached in localStorage after login/signup.
'use client'
export interface Session { token: string; name: string; email: string }
const KEY = 'tl-session'
export function loadSession(): Session | null {
  try {
    const raw = localStorage.getItem(KEY)
    return raw ? JSON.parse(raw) as Session : null
  } catch { return null }
}
export function saveSession(s: Session) {
  localStorage.setItem(KEY, JSON.stringify(s))
  window.dispatchEvent(new Event('tl-auth'))
}
export function clearSession() {
  localStorage.removeItem(KEY)
  window.dispatchEvent(new Event('tl-auth'))
}
export function authHeaders(): Record<string, string> {
  const s = loadSession()
  return s ? { Authorization: `Bearer ${s.token}` } : {}
}
