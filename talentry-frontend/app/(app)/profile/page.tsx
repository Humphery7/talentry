import type { Metadata } from 'next'
import { ProfileEditor } from '@/components/CandidateProfile'
import { PageHead } from '@/components/ui'
export const metadata: Metadata = { title: 'Your profile' }
export default function Page() {
  return (
    <>
      <PageHead title="Your profile" sub="Your CV is the one thing auto-apply needs. The rest is optional, but the more you add, the fewer questions you’ll have to answer later and the better your matches." />
      <ProfileEditor />
    </>
  )
}
