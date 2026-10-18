import { NextResponse } from 'next/server'
// Forwards signup/login to the backend, which hashes (bcrypt) and returns a JWT.
// The browser stores the token (lib/auth.ts) and sends it back as a Bearer.
const API = process.env.API_URL ?? 'http://localhost:3001'
export async function POST(req: Request, { params }: { params: Promise<{ mode: string }> }) {
  const { mode } = await params
  if (mode !== 'login' && mode !== 'signup') return NextResponse.json({ error: 'Not found' }, { status: 404 })
  const body = await req.json().catch(() => null)
  const r = await fetch(`${API}/auth/${mode}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  return NextResponse.json(await r.json(), { status: r.status })
}
