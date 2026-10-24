import type { Metadata } from 'next'
import { ProfileEditor } from '@/components/CandidateProfile'
import { PageHead } from '@/components/ui'
export const metadata: Metadata = { title: 'Your profile' }
export default function Page() {
  return (
    <>
      <PageHead title="Your profile" sub="A few details help us match you with the right roles. Everything here is optional." />
      <ProfileEditor />
    </>
  )
}
