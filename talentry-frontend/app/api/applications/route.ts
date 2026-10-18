import { NextResponse } from 'next/server'
// Forwards the client's Bearer token to the protected backend endpoint.
const API = process.env.API_URL ?? 'http://localhost:3001'
export async function POST(req: Request) {
  const { jobId } = await req.json().catch(() => ({}))
  if (typeof jobId !== 'number') return NextResponse.json({ error: 'Invalid jobId' }, { status: 400 })
  const r = await fetch(`${API}/applications`, {
    method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: req.headers.get('authorization') ?? '' },
    body: JSON.stringify({ jobId }),
  })
  return NextResponse.json(await r.json(), { status: r.status })
}
