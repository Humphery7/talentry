'use client'
import { useCallback, useEffect, useState } from 'react'
const KEY = 'tl-saved'
const read = (): number[] => { try { return JSON.parse(localStorage.getItem(KEY) || '[]') } catch { return [] } }
// Swap localStorage for POST/DELETE /api/saved once you have auth.
export function useSaved() {
  const [ids, set] = useState<number[]>([]), [ready, setReady] = useState(false)
  useEffect(() => { const f = () => set(read()); f(); setReady(true); window.addEventListener('tl-saved', f); return () => window.removeEventListener('tl-saved', f) }, [])
  const toggle = useCallback((id: number) => {
    const c = read(), n = c.includes(id) ? c.filter(x => x !== id) : [...c, id]
    try { localStorage.setItem(KEY, JSON.stringify(n)) } catch {}
    window.dispatchEvent(new Event('tl-saved'))
  }, [])
  return { ids, toggle, ready }
}
