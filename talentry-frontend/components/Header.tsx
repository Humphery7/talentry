'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useState } from 'react'
import { clearSession, loadSession, type Session } from '@/lib/auth'
import { Icon } from './ui'
const NAV = [['/jobs', 'Find Jobs'], ['/companies', 'Companies'], ['/cv', 'AI CV Analysis'], ['/interview', 'Mock Interview'], ['/coach', 'Career Coach'], ['/about', 'About']]
export default function Header() {
  const path = usePathname()
  const [user, setUser] = useState<Session | null>(null)
  useEffect(() => {
    const sync = () => setUser(loadSession())
    sync()
    window.addEventListener('tl-auth', sync)
    return () => window.removeEventListener('tl-auth', sync)
  }, [])
  const on = (h: string) => path.startsWith(h) || (h === '/jobs' && path === '/saved')
  return (
    <header className="top">
      <Link href="/" className="logo" style={{ textDecoration: 'none' }}><b>tale</b>ntry</Link>
      <nav aria-label="Primary">{NAV.map(([h, t]) => <Link key={h} href={h} aria-current={on(h) ? 'page' : undefined}>{t}</Link>)}</nav>
      <div className="acts">
        <button className="ib" aria-label="Messages"><Icon n="mail" /><span className="dot" /></button>
        <button className="ib" aria-label="Notifications"><Icon n="bell" /></button>
        {user
          ? <button className="av" aria-label={`Log out ${user.name}`} title={`Log out ${user.name}`} onClick={clearSession}>{user.name.slice(0, 1).toUpperCase()}</button>
          : <Link href="/?auth=login" className="av" aria-label="Log in" style={{ textDecoration: 'none' }}>?</Link>}
      </div>
    </header>
  )
}
