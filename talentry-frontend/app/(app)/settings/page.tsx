import type { Metadata } from 'next'
import AiSettings from '@/components/AiSettings'
import { PageHead } from '@/components/ui'

export const metadata: Metadata = { title: 'Settings' }

export default function Page() {
  return (
    <>
      <PageHead
        title="Settings"
        sub="Connect the AI account Talentry should use for your requests."
      />
      <AiSettings />
    </>
  )
}
