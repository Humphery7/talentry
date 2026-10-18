'use client'
import { useEffect, useRef, useState } from 'react'
import { PageHead } from './ui'
const QS = ['Tell me about yourself.', 'Describe a design decision you had to defend.', 'How do you handle conflicting feedback?', 'Walk me through a project you shipped end to end.']
export function Interview() {
  const [i, setI] = useState(0), [x, setX] = useState(''), [w, setW] = useState<number[]>([]), words = x.trim() ? x.trim().split(/\s+/).length : 0
  return (<div><PageHead title="Mock interview" sub="Write your answer as if speaking. Aim for 60 to 120 words." />
    <div className="panel"><div className="bar"><i style={{ transform: `scaleX(${i / QS.length})` }} /></div>
      {i >= QS.length ? <div><h2 style={{ margin: '22px 0 8px' }}>Session complete</h2><p style={{ color: 'var(--mute)', marginBottom: 20 }}>{QS.length} answers, averaging {Math.round(w.reduce((s, n) => s + n, 0) / QS.length)} words each.</p>
        <button className="btn" style={{ maxWidth: 220 }} onClick={() => { setI(0); setW([]) }}>Practice again</button></div>
      : <div><p style={{ color: 'var(--mute)', marginTop: 18 }}>Question {i + 1} of {QS.length}</p><h2>{QS[i]}</h2>
        <textarea className="f" aria-label="Your answer" value={x} onChange={e => setX(e.target.value)} />
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}><span className="m">{words} words</span>
          <button className="btn" style={{ maxWidth: 200 }} disabled={!words} onClick={() => { setW(v => [...v, words]); setX(''); setI(i + 1) }}>{i === QS.length - 1 ? 'Finish' : 'Next question'}</button></div></div>}
    </div></div>)
}
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
