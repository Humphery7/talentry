import { NextResponse } from 'next/server'
const API = process.env.API_URL ?? 'http://localhost:3001'
export async function GET(_: Request, { params }: { params: Promise<{ id: string }> }) {
  const r = await fetch(`${API}/jobs/${(await params).id}`, { cache: 'no-store' })
  return NextResponse.json(await r.json(), { status: r.status })
}
