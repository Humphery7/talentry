'use client'
import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { saveSession } from '@/lib/auth'
// After a Google login the backend redirects here with the JWT in the URL hash.
// This reads it once, stores the session, then clears the hash so it is not
// left in the address bar or browser history.
export default function AuthToken() {
  const router = useRouter()
  useEffect(() => {
    const params = new URLSearchParams(window.location.hash.slice(1))
    const token = params.get('token')
    if (!token) return
    saveSession({ token, name: params.get('name') ?? '', email: params.get('email') ?? '' })
    window.history.replaceState(null, '', window.location.pathname + window.location.search)
    router.refresh()
  }, [router])
  return null
}
