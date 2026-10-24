import { ProfilePrompt } from '@/components/CandidateProfile'
import Header from '@/components/Header'
import Rail from '@/components/Rail'
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return <div className="app-root"><div className="shell"><Header /><Rail /><div className="wrap">{children}</div><ProfilePrompt /></div></div>
}
