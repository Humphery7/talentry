'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Icon } from './ui'
const L = [['user', '/about', 'About'], ['bm', '/saved', 'Saved jobs'], ['file', '/cv', 'CV analysis'], ['cal', '/interview', 'Mock interview'], ['clock', '/coach', 'Career coach']] as const
export default function Rail() {
  const path = usePathname()
  const theme = () => { const r = document.documentElement, n = r.dataset.theme === 'dark' ? 'light' : 'dark'; r.dataset.theme = n; try { localStorage.setItem('tl-theme', n) } catch {} }
  return (
    <div className="rail"><nav className="rail-in" aria-label="Shortcuts">
      {L.map(([i, h, l]) => <Link key={h} href={h} className="rb" aria-label={l} aria-current={path === h ? 'page' : undefined}><Icon n={i} /></Link>)}
      <button className="rb" aria-label="Toggle theme" onClick={theme}><Icon n="set" /></button>
    </nav></div>
  )
}
