import Link from 'next/link'

export default function PublicLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="app-root"><div className="shell">
      <header className="top">
        <Link href="/" className="logo" style={{ textDecoration: 'none' }}><b>tale</b>ntry</Link>
        <nav aria-label="Primary">
          <Link href="/jobs">Find Jobs</Link>
          <Link href="/about" aria-current="page">About</Link>
        </nav>
        <div className="acts">
          <Link href="/?auth=login" scroll={false} className="chip" style={{ textDecoration: 'none' }}>Log in</Link>
          <Link href="/?auth=signup" scroll={false} className="chip" style={{ textDecoration: 'none' }}>Get started</Link>
        </div>
      </header>
      <div style={{ padding: '0 16px' }}>{children}</div>
    </div></div>
  )
}
