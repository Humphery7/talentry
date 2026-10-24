import { NextResponse } from 'next/server'
// Forwards raw CV uploads/downloads to the Express API with the user's token.
const API = process.env.API_URL ?? 'http://localhost:3001'

export async function PUT(req: Request) {
  const body = await req.arrayBuffer()
  const r = await fetch(`${API}/candidate-profile/cv`, {
    method: 'PUT',
    headers: {
      Authorization: req.headers.get('authorization') ?? '',
      'Content-Type': req.headers.get('content-type') ?? 'application/octet-stream',
      'X-Filename': req.headers.get('x-filename') ?? 'cv',
    },
    body,
    cache: 'no-store',
  })
  const data = await r.json().catch(() => null)
  return NextResponse.json(data, { status: r.status })
}

export async function GET(req: Request) {
  const r = await fetch(`${API}/candidate-profile/cv`, {
    headers: { Authorization: req.headers.get('authorization') ?? '' },
    cache: 'no-store',
  })
  if (!r.ok) {
    const data = await r.json().catch(() => null)
    return NextResponse.json(data, { status: r.status })
  }
  return new NextResponse(await r.arrayBuffer(), {
    headers: {
      'Content-Type': r.headers.get('content-type') ?? 'application/octet-stream',
      'Content-Disposition': r.headers.get('content-disposition') ?? 'attachment',
    },
  })
}
