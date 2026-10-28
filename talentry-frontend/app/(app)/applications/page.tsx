import type { Metadata } from 'next'
import ApplicationsList from '@/components/ApplicationsList'

export const metadata: Metadata = { title: 'Applications' }

export default function Page() {
  return <ApplicationsList />
}
