import { NextResponse } from 'next/server'
// Forwards the logged-in user's Gemini key settings to the Express API. The
// key is sent up once and only a masked hint is ever returned.
const API = process.env.API_URL ?? 'http://localhost:3001'

async function forward(req: Request, method: 'GET' | 'PUT' | 'DELETE', body?: unknown) {
  const r = await fetch(`${API}/settings/ai`, {
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

export async function DELETE(req: Request) {
  return forward(req, 'DELETE')
}
