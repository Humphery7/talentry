import type { Metadata } from 'next'
import { CareerCoach } from '@/components/CareerCoach'
import { getJobFacets } from '@/lib/api'

export const metadata: Metadata = { title: 'Career Coach' }

export default async function Page() {
  // The coach uses the same scope controls as the jobs page, so it needs the
  // same counts. Fetching here keeps CareerCoach a client component.
  const facets = await getJobFacets()
  return <CareerCoach facets={facets} />
}
