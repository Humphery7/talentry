'use client'
import { useEffect, useRef, useState } from 'react'
import { PageHead } from './ui'
const ANS: Record<string, string> = { 'Salary negotiation': 'Anchor with market data, state a range whose bottom is your target, then pause.', 'Switching careers': 'Lead with transferable results, add one portfolio project in the new field, apply to adjacent roles.', 'Portfolio review': 'Show three projects: the problem, your role, and a measurable outcome.' }
export function Coach() {
  const [m, setM] = useState<[string, string][]>([['bot', 'Pick a topic for a quick playbook.']])
  return (<div><PageHead title="Career coach" sub="Sample guidance. Connect your API for a live coach." />
    <div className="panel"><div className="msgs">{m.map(([r, t], i) => <div key={i} className={'m1' + (r === 'me' ? ' me' : '')}>{t}</div>)}</div>
      <div className="chips">{Object.keys(ANS).map(t => <button key={t} className="chip" onClick={() => setM(v => [...v, ['me', t], ['bot', ANS[t]]])}>{t}</button>)}</div></div></div>)
}
export function CV() {
  const [name, setName] = useState(''), [go, setGo] = useState(false), ref = useRef<HTMLInputElement>(null), C = 2 * Math.PI * 70
  useEffect(() => { const t = setTimeout(() => setGo(true), 80); return () => clearTimeout(t) }, [])
  const tips = [['Quantify results', 'Add numbers to your last three roles.'], ['Tighten your summary', 'Keep it to three lines.'], ['Match keywords', 'Mirror terms from roles you want.']]
  return (<div><PageHead title="AI CV Analysis" sub="Sample report. Connect your API to score uploaded files." />
    <div className="two"><div className="panel" style={{ textAlign: 'center' }}>
      <svg className="ring" viewBox="0 0 160 160" role="img" aria-label="CV score 87 of 100"><circle className="tr" cx="80" cy="80" r="70" />
        <circle className="pr" cx="80" cy="80" r="70" strokeDasharray={C} strokeDashoffset={go ? C * .13 : C} transform="rotate(-90 80 80)" />
        <text x="80" y="92" textAnchor="middle" fontSize="38" fill="currentColor" stroke="none">87</text></svg>
      <p style={{ margin: '16px 0', color: 'var(--mute)' }}>{name || 'No CV uploaded'}</p>
      <input ref={ref} type="file" hidden onChange={e => setName(e.target.files?.[0]?.name ?? '')} /><button className="btn" onClick={() => ref.current?.click()}>Upload CV</button></div>
      <div className="panel"><h2 style={{ marginBottom: 10 }}>Suggestions</h2>{tips.map(([t, d]) => <div key={t} className="tip"><b>{t}</b><span>{d}</span></div>)}</div></div></div>)
}
