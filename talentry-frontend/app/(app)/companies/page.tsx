import Link from 'next/link'
import type { Metadata } from 'next'
import { getCompanies } from '@/lib/api'
import { CompanyLogo, PageHead } from '@/components/ui'
export const metadata: Metadata = { title: 'Companies' }
export default async function Companies() {
  const cs = await getCompanies()
  return (<div><PageHead title="Companies" sub="Browse hiring teams and jump straight to their open roles." />
    <div className="cgrid">{cs.map(c => <Link key={c.slug} href={`/jobs?co=${encodeURIComponent(c.slug)}&lo=0&hi=200`} className="cc" style={{ textDecoration: 'none' }}>
      <CompanyLogo job={{ bg: `hsl(0 0% 20%)`, ch: c.name.slice(0, 1).toUpperCase() }} /><b>{c.name}</b><span className="m">{c.industry ?? ''}</span><span className="m">{c.openRoles ?? 0} open role(s)</span></Link>)}</div></div>)
}
