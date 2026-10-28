import { NextResponse } from 'next/server'

// Forwards application-agent actions to the Express API with the user's token.
const API = process.env.API_URL ?? 'http://localhost:3001'

type Context = { params: Promise<{ path: string[] }> }

async function forward(req: Request, { params }: Context) {
  const { path } = await params
  const search = new URL(req.url).search
  const body =
    req.method === 'GET' || req.method === 'HEAD' ? undefined : await req.text()
  const r = await fetch(
    `${API}/agent-applications/${path.map(encodeURIComponent).join('/')}${search}`,
    {
      method: req.method,
      headers: {
        ...(body
          ? { 'Content-Type': req.headers.get('content-type') ?? 'application/json' }
          : {}),
        Authorization: req.headers.get('authorization') ?? '',
      },
      body: body || undefined,
      cache: 'no-store',
    },
  )
  const data = await r.text()
  return new NextResponse(data, {
    status: r.status,
    headers: { 'Content-Type': r.headers.get('content-type') ?? 'application/json' },
  })
}

export { forward as GET, forward as POST, forward as PUT }
