import type { Metadata } from 'next'
import ApplicationDetail from '@/components/ApplicationDetail'

export const metadata: Metadata = { title: 'Application' }

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  return <ApplicationDetail id={(await params).id} />
}
