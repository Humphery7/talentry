import { NextResponse } from 'next/server'
// Forwards recommendation reads/refreshes to the Express API with the user's token.
const API = process.env.API_URL ?? 'http://localhost:3001'

async function forward(req: Request, method: 'GET' | 'POST', path: string) {
  const r = await fetch(`${API}${path}`, {
    method,
    headers: { Authorization: req.headers.get('authorization') ?? '' },
    cache: 'no-store',
  })
  const data = await r.json().catch(() => null)
  return NextResponse.json(data, { status: r.status })
}

export async function GET(req: Request) {
  return forward(req, 'GET', '/recommendations')
}

export async function POST(req: Request) {
  return forward(req, 'POST', '/recommendations/refresh')
}
