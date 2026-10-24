import type { Metadata } from 'next'
import { Suspense } from 'react'
import InterviewPrep from '@/components/InterviewPrep'
export const metadata: Metadata = { title: 'Interview prep' }
export default function Page() {
  return (
    <Suspense fallback={<div className="panel">Loading interview prep…</div>}>
      <InterviewPrep />
    </Suspense>
  )
}
