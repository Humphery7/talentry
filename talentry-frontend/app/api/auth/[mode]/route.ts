import { NextResponse } from 'next/server'
import { AUTH_COOKIE, authCookie } from '@/lib/auth-cookie'
// Forwards signup/login to the backend, which hashes (bcrypt) and returns a JWT.
// The browser stores the token (lib/auth.ts) and sends it back as a Bearer.
// We also mirror it into an httpOnly cookie so middleware can gate server routes.
const API = process.env.API_URL ?? 'http://localhost:3001'
export async function POST(req: Request, { params }: { params: Promise<{ mode: string }> }) {
  const { mode } = await params
  if (mode !== 'login' && mode !== 'signup') return NextResponse.json({ error: 'Not found' }, { status: 404 })
  const body = await req.json().catch(() => null)
  const r = await fetch(`${API}/auth/${mode}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  const data = await r.json().catch(() => null)
  const res = NextResponse.json(data, { status: r.status })
  const token = data && typeof data.accessToken === 'string' ? data.accessToken : null
  if (r.ok && token) res.cookies.set(AUTH_COOKIE, token, authCookie)
  return res
}
