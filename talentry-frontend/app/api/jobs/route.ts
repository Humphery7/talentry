import { NextRequest, NextResponse } from 'next/server'
// Proxy to the NestJS backend so the browser stays same-origin.
const API = process.env.API_URL ?? 'http://localhost:3001'
export async function GET(req: NextRequest) {
  const r = await fetch(`${API}/jobs?${req.nextUrl.searchParams}`, { cache: 'no-store' })
  return NextResponse.json(await r.json(), { status: r.status })
}
