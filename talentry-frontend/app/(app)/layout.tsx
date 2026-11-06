import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import { ProfilePrompt } from '@/components/CandidateProfile'
import Header from '@/components/Header'
import Rail from '@/components/Rail'
import { AUTH_COOKIE } from '@/lib/auth-cookie'

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const token = (await cookies()).get(AUTH_COOKIE)?.value
  if (!token) redirect('/?auth=login')
  return <div className="app-root"><div className="shell"><Header /><Rail /><div className="wrap">{children}</div><ProfilePrompt /></div></div>
}
