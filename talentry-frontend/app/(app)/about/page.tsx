import type { Metadata } from 'next'
import { PageHead } from '@/components/ui'
export const metadata: Metadata = { title: 'About' }
export default function About() {
  return (<div><PageHead title="About talentry" sub="One place to find roles, sharpen your CV, and rehearse interviews." />
    <div className="cgrid">{[['9', 'sample roles'], ['6', 'companies'], ['4', 'practice questions']].map(([n, l]) => <div key={l} className="panel"><div className="big">{n}</div><span className="m">{l}</span></div>)}</div></div>)
}
