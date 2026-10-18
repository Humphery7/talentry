import type { Metadata } from 'next'
import { Interview } from '@/components/Practice'
export const metadata: Metadata = { title: 'Mock Interview' }
export default function Page() { return <Interview /> }
