'use client'
import { useEffect, useRef, useState } from 'react'
import { PageHead } from './ui'
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
