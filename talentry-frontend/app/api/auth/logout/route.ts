import { NextResponse } from 'next/server'
import { AUTH_COOKIE, authCookie } from '@/lib/auth-cookie'

export async function POST() {
  const res = NextResponse.json({ ok: true })
  res.cookies.set(AUTH_COOKIE, '', { ...authCookie, maxAge: 0 })
  return res
}
