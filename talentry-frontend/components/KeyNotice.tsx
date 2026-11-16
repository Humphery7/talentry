'use client'

import Link from 'next/link'

/**
 * Shown when the server answers 428: the feature needs a Gemini key that the
 * user has not saved yet. It links straight to Settings instead of making them
 * guess what to do.
 */
export default function KeyNotice({ message }: { message?: string }) {
  return (
    <div className="panel" role="status" style={{ margin: '12px 0' }}>
      <b>Add your Gemini API key</b>
      <p style={{ margin: '6px 0 0' }}>
        {message ??
          'This feature uses Gemini, and Talentry needs your own key to run it. Add one in Settings, then try again.'}
      </p>
      <p style={{ margin: '10px 0 0' }}>
        <Link href="/settings">Open Settings</Link>
      </p>
    </div>
  )
}
