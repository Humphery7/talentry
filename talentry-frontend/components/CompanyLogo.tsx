'use client'

import { useEffect, useRef, useState } from 'react'
import type { Job } from '@/lib/data'

/**
 * Company avatar: the real logo the crawler stored, with the coloured
 * initials as a fallback for the few companies that have none (or whose
 * image fails to load).
 */
export default function CompanyLogo({
  job,
}: {
  job: Pick<Job, 'bg' | 'ch'> & { logo?: string | null }
}) {
  const [failed, setFailed] = useState(false)
  const img = useRef<HTMLImageElement>(null)
  const logo = job.logo
  const showLogo = Boolean(logo) && !failed

  // An image that fails while the page is still server-rendered fires its
  // error before React has attached onError, so check once after hydration.
  useEffect(() => {
    const el = img.current
    if (el && el.complete && el.naturalWidth === 0) setFailed(true)
  }, [logo])

  return (
    <span
      className={'logo-c' + (showLogo ? ' has-logo' : '')}
      aria-hidden="true"
      style={
        showLogo
          ? undefined
          : {
              background: job.bg,
              color: job.bg === '#fff' ? '#4285f4' : '#fff',
              border: job.bg === '#fff' ? '1px solid #eee' : 0,
              fontSize: job.ch.length > 3 ? 11 : 22,
            }
      }
    >
      {showLogo ? (
        // eslint-disable-next-line @next/next/no-img-element -- remote logos come
        // from a CDN that is not in next.config's remotePatterns; a plain img
        // keeps the fallback simple and avoids proxying every company mark.
        <img
          ref={img}
          src={logo ?? ''}
          alt=""
          loading="lazy"
          decoding="async"
          referrerPolicy="no-referrer"
          onError={() => setFailed(true)}
        />
      ) : (
        job.ch
      )}
    </span>
  )
}
