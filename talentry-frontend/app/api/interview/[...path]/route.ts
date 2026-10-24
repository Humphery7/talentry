import { NextResponse } from 'next/server'

// Forwards interview requests to the Express backend with the user's token.
// The browser never talks to talentry-career directly.
const API = process.env.API_URL ?? 'http://localhost:3001'

type Context = { params: Promise<{ path: string[] }> }

async function forward(req: Request, { params }: Context) {
  const { path } = await params
  const search = new URL(req.url).search
  const body =
    req.method === 'GET' || req.method === 'HEAD' ? undefined : await req.text()

  const r = await fetch(`${API}/interview/${path.join('/')}${search}`, {
    method: req.method,
    headers: {
      ...(body
        ? { 'Content-Type': req.headers.get('content-type') ?? 'application/json' }
        : {}),
      Authorization: req.headers.get('authorization') ?? '',
    },
    body,
    cache: 'no-store',
  })

  const data = await r.text()
  return new NextResponse(data, {
    status: r.status,
    headers: {
      'Content-Type': r.headers.get('content-type') ?? 'application/json',
    },
  })
}

export {
  forward as GET,
  forward as POST,
  forward as PUT,
}
