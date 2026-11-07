import { NextResponse, type NextRequest } from 'next/server'
import { AUTH_COOKIE, authCookie } from '@/lib/auth-cookie'

const API = process.env.API_URL ?? 'http://localhost:3001'

function loginRedirect(req: NextRequest) {
  const url = new URL('/?auth=login', req.url)
  url.searchParams.set('next', `${req.nextUrl.pathname}${req.nextUrl.search}`)
  return url
}

export async function middleware(req: NextRequest) {
  const token = req.cookies.get(AUTH_COOKIE)?.value
  if (!token) return NextResponse.redirect(loginRedirect(req))

  let valid = false
  try {
    const r = await fetch(`${API}/auth/profile`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: 'no-store',
    })
    valid = r.ok
  } catch {
    valid = false
  }

  if (valid) return NextResponse.next()

  const res = NextResponse.redirect(loginRedirect(req))
  res.cookies.set(AUTH_COOKIE, '', { ...authCookie, maxAge: 0 })
  return res
}

export const config = {
  matcher: [
    '/jobs',
    '/jobs/:path*',
    '/companies',
    '/companies/:path*',
    '/applications',
    '/applications/:path*',
    '/saved',
    '/saved/:path*',
    '/profile',
    '/profile/:path*',
    '/interview',
    '/interview/:path*',
    '/coach',
    '/coach/:path*',
  ],
}
