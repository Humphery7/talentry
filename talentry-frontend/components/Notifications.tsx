'use client'
import Link from 'next/link'
import { useCallback, useEffect, useRef, useState } from 'react'
import { loadSession } from '@/lib/auth'
import { notificationCall } from '@/lib/applications'
import { Icon } from './ui'

interface Notification {
  id: string
  applicationId: string | null
  title: string
  body: string
  readAt: string | null
  createdAt: string
}

export default function Notifications() {
  const [data, setData] = useState<{ unread: number; items: Notification[] }>({ unread: 0, items: [] })
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)

  const load = useCallback(async () => {
    if (!loadSession()) { setData({ unread: 0, items: [] }); return }
    try { setData(await notificationCall('')) } catch { /* keep the last list */ }
  }, [])

  useEffect(() => {
    void load()
    const timer = setInterval(load, 20000)
    window.addEventListener('tl-auth', load)
    return () => { clearInterval(timer); window.removeEventListener('tl-auth', load) }
  }, [load])

  useEffect(() => {
    if (!open) return
    const onDoc = (event: MouseEvent) => { if (box.current && !box.current.contains(event.target as Node)) setOpen(false) }
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDoc); document.removeEventListener('keydown', onKey) }
  }, [open])

  async function toggle() {
    setOpen(value => !value)
    if (!open && data.unread) {
      await notificationCall('/read', 'POST', { ids: 'all' }).catch(() => undefined)
      setTimeout(load, 1500)
    }
  }

  return (
    <div className="account" ref={box}>
      <button className="ib" aria-label={`Notifications${data.unread ? `, ${data.unread} unread` : ''}`} aria-haspopup="menu" aria-expanded={open} onClick={() => void toggle()}>
        <Icon n="bell" />{data.unread > 0 && <span className="dot" />}
      </button>
      {open && (
        <div className="usermenu" role="menu" style={{ width: 320, maxHeight: 400, overflow: 'auto' }}>
          {data.items.length === 0 && <div className="uinfo"><span>No notifications yet.</span></div>}
          {data.items.map(item => (
            <Link key={item.id} role="menuitem" className="usermenu-item" style={{ display: 'block', whiteSpace: 'normal', fontWeight: item.readAt ? 400 : 600 }}
              href={item.applicationId ? `/applications/${item.applicationId}` : '/applications'} onClick={() => setOpen(false)}>
              {item.title}
              <div className="m" style={{ fontWeight: 400 }}>{item.body}</div>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
