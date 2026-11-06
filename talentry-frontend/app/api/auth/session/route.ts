import { NextResponse, type NextRequest } from 'next/server'
import { AUTH_COOKIE, authCookie } from '@/lib/auth-cookie'

const API = process.env.API_URL ?? 'http://localhost:3001'

// Called after a Google login hands the token back in the URL hash. The token
// is checked against the backend before it is promoted to an httpOnly cookie.
export async function POST(req: NextRequest) {
  const body = (await req.json().catch(() => null)) as { token?: unknown } | null
  const token = typeof body?.token === 'string' ? body.token : ''
  if (!token) return NextResponse.json({ error: 'Missing token.' }, { status: 400 })

  const r = await fetch(`${API}/auth/profile`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: 'no-store',
  })
  if (!r.ok) return NextResponse.json({ error: 'Invalid or expired token.' }, { status: 401 })

  const user = await r.json().catch(() => null)
  if (!user || typeof user !== 'object') {
    return NextResponse.json({ error: 'Invalid token.' }, { status: 401 })
  }

  const res = NextResponse.json({ user })
  res.cookies.set(AUTH_COOKIE, token, authCookie)
  return res
}
