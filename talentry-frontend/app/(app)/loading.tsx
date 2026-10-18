export default function Loading() {
  return (
    <div aria-busy="true" aria-label="Loading">
      <div className="sk" style={{ minHeight: 64, width: 'min(520px,70%)', margin: '68px 0 20px' }} />
      <div className="grid" style={{ marginTop: 34 }}>{Array.from({ length: 6 }, (_, i) => <div key={i} className="sk" />)}</div>
    </div>
  )
}
