import { ImageResponse } from 'next/og'
export const size = { width: 180, height: 180 }
export const contentType = 'image/png'
export default function AppleIcon() {
  return new ImageResponse(
    <div style={{ width: '100%', height: '100%', display: 'flex', background: 'linear-gradient(135deg,#3d3d3d,#000)' }}>
      <svg width="180" height="180" viewBox="0 0 64 64"><g fill="none" stroke="#fff" strokeWidth="7" strokeLinecap="round" strokeLinejoin="round"><path d="M32 15v26c0 4 2.5 6 7 6" /><path d="M22 25h20" /></g></svg>
    </div>, size)
}
