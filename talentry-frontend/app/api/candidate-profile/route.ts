import { NextResponse } from 'next/server'
// Forwards the logged-in user's candidate profile to the Express API.
const API = process.env.API_URL ?? 'http://localhost:3001'

async function forward(req: Request, method: 'GET' | 'PUT', body?: unknown) {
  const r = await fetch(`${API}/candidate-profile`, {
    method,
    headers: {
      Authorization: req.headers.get('authorization') ?? '',
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
    cache: 'no-store',
  })
  const data = await r.json().catch(() => null)
  return NextResponse.json(data, { status: r.status })
}

export async function GET(req: Request) {
  return forward(req, 'GET')
}

export async function PUT(req: Request) {
  const body = await req.json().catch(() => null)
  return forward(req, 'PUT', body)
}
