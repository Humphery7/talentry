import type { Metadata } from 'next'
import { Coach } from '@/components/Practice'
export const metadata: Metadata = { title: 'Career Coach' }
export default function Page() { return <Coach /> }
