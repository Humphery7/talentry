import './globals.css'
import type { Metadata, Viewport } from 'next'
export const metadata: Metadata = { title: { default: 'Talentry', template: '%s · Talentry' }, description: 'Find verified jobs and scholarships that match your skills and goals.' }
export const viewport: Viewport = { width: 'device-width', initialScale: 1, viewportFit: 'cover' }
// Applies the saved theme before first paint so there is no flash.
const themeScript = `try{var t=localStorage.getItem('tl-theme');if(t)document.documentElement.dataset.theme=t}catch(e){}`
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="light" suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: themeScript }} /></head>
      <body>{children}</body>
    </html>
  )
}
