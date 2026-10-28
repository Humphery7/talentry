import { NextResponse } from 'next/server'

const API = process.env.API_URL ?? 'http://localhost:3001'

async function forward(req: Request, method: 'GET' | 'POST') {
  const body = method === 'GET' ? undefined : await req.text()
  const r = await fetch(`${API}/agent-applications`, {
    method,
    headers: {
      ...(body ? { 'Content-Type': 'application/json' } : {}),
      Authorization: req.headers.get('authorization') ?? '',
    },
    body: body || undefined,
    cache: 'no-store',
  })
  const data = await r.text()
  return new NextResponse(data, {
    status: r.status,
    headers: { 'Content-Type': r.headers.get('content-type') ?? 'application/json' },
  })
}

export async function GET(req: Request) {
  return forward(req, 'GET')
}

export async function POST(req: Request) {
  return forward(req, 'POST')
}
