'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useRef, useState } from 'react'
import { clearSession, loadSession, type Session } from '@/lib/auth'
import { Icon } from './ui'
const NAV = [['/jobs', 'Find Jobs'], ['/companies', 'Companies'], ['/cv', 'AI CV Analysis'], ['/interview', 'Mock Interview'], ['/coach', 'Career Coach'], ['/about', 'About']]
export default function Header() {
  const path = usePathname()
  const [user, setUser] = useState<Session | null>(null)
  const [menu, setMenu] = useState(false)
  const account = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const sync = () => setUser(loadSession())
    sync()
    window.addEventListener('tl-auth', sync)
    return () => window.removeEventListener('tl-auth', sync)
  }, [])
  useEffect(() => {
    if (!menu) return
    const onDoc = (e: MouseEvent) => { if (account.current && !account.current.contains(e.target as Node)) setMenu(false) }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setMenu(false) }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDoc); document.removeEventListener('keydown', onKey) }
  }, [menu])
  const on = (h: string) => path.startsWith(h) || (h === '/jobs' && path === '/saved')
  return (
    <header className="top">
      <Link href="/" className="logo" style={{ textDecoration: 'none' }}><b>tale</b>ntry</Link>
      <nav aria-label="Primary">{NAV.map(([h, t]) => <Link key={h} href={h} aria-current={on(h) ? 'page' : undefined}>{t}</Link>)}</nav>
      <div className="acts">
        <button className="ib" aria-label="Messages"><Icon n="mail" /><span className="dot" /></button>
        <button className="ib" aria-label="Notifications"><Icon n="bell" /></button>
        {user
          ? <div className="account" ref={account}>
            <button className="av" aria-label="Account menu" aria-haspopup="menu" aria-expanded={menu} onClick={() => setMenu(v => !v)}>{user.name.slice(0, 1).toUpperCase()}</button>
            {menu && <div className="usermenu" role="menu">
              <div className="uinfo"><b>{user.name}</b><span>{user.email}</span></div>
              <Link href="/profile" role="menuitem" className="usermenu-item" onClick={() => setMenu(false)}>Profile</Link>
              <button type="button" role="menuitem" className="usermenu-item" onClick={() => { clearSession(); setMenu(false) }}>Sign out</button>
            </div>}
          </div>
          : <Link href="/?auth=login" className="av" aria-label="Log in" style={{ textDecoration: 'none' }}>?</Link>}
      </div>
    </header>
  )
}
