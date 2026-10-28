'use client'

import Link from 'next/link'
import { useCallback, useEffect, useState } from 'react'
import { applyWithAgent } from '@/lib/applications'
import {
  listRecommendations,
  refreshRecommendations,
  type Recommendation,
  type Recommendations,
} from '@/lib/recommendations'
import { type CandidateProfile, useCandidateProfile } from './CandidateProfile'
import { PageHead } from './ui'

function message(err: unknown): string {
  return err instanceof Error ? err.message : 'Something went wrong. Try again.'
}

function hasProfileDetails(profile: CandidateProfile): boolean {
  return Boolean(
    profile.headline?.trim() ||
      profile.currentTitle?.trim() ||
      profile.location?.trim() ||
      profile.summary?.trim() ||
      profile.cvFilename ||
      profile.yearsExperience !== null,
  )
}

function staleReasons(meta: Recommendations['meta']): string {
  const reasons: string[] = []
  if (meta.profileChanged) reasons.push('your profile changed')
  if (meta.newJobs > 0) {
    reasons.push(
      `${meta.newJobs} new or updated ${
        meta.newJobs === 1 ? 'job is' : 'jobs are'
      } available`,
    )
  }
  return reasons.join(' and ')
}

function recommendationTags(item: Recommendation): string[] {
  const tags = [
    item.seniority,
    item.occupation?.replace(/-/g, ' '),
    item.employmentType,
    item.workplaceType,
  ].filter((value): value is string => Boolean(value))
  return [...new Set(tags)]
}

function RecommendationCard({
  item,
  selected,
  queued,
  onToggle,
}: {
  item: Recommendation
  selected: boolean
  queued: boolean
  onToggle: (jobId: number) => void
}) {
  const tags = recommendationTags(item)
  return (
    <article
      className={`panel rec${selected ? ' is-selected' : ''}${
        queued ? ' is-queued' : ''
      }`}
    >
      <div className="rec-top">
        <span className="rec-rank">#{item.rank}</span>
        <span className="rec-score">{Math.round(item.score)}% match</span>
      </div>
      <h3><Link href={`/jobs/${item.jobId}`}>{item.title}</Link></h3>
      <p className="m">
        {item.company || 'Company'} ·{' '}
        {item.locations.join(', ') || 'Location not listed'}
      </p>
      {item.reason ? <p className="rec-reason">{item.reason}</p> : null}
      {tags.length ? (
        <div className="tags">
          {tags.map(tag => <span key={tag}>{tag}</span>)}
        </div>
      ) : null}
      <label className={`rec-select${queued ? ' is-queued' : ''}`}>
        <input
          type="checkbox"
          checked={selected || queued}
          disabled={queued}
          onChange={() => onToggle(item.jobId)}
        />
        {queued ? 'Queued with Talentry' : 'Apply with Talentry agent'}
      </label>
      <div className="rec-actions">
        <a
          href={item.url}
          target="_blank"
          rel="noreferrer"
          className="btn rec-btn"
        >
          Apply manually
        </a>
        <Link href={`/jobs/${item.jobId}`} className="btn rec-btn rec-btn-ghost">
          View job
        </Link>
        <Link
          href={`/interview?jobId=${item.jobId}`}
          className="btn rec-btn rec-btn-ghost"
        >
          Interview prep
        </Link>
      </div>
    </article>
  )
}

export function CareerCoach() {
  const { user, profile } = useCandidateProfile()
  const [recs, setRecs] = useState<Recommendations | null>(null)
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [queued, setQueued] = useState<Set<number>>(new Set())
  const [agentBusy, setAgentBusy] = useState(false)
  const [agentError, setAgentError] = useState('')
  const [agentNotice, setAgentNotice] = useState('')

  const email = user?.email
  const ready = Boolean(profile && hasProfileDetails(profile))

  const load = useCallback(async () => {
    if (!email || !ready) {
      setRecs(null)
      return
    }
    setLoading(true)
    setError('')
    try {
      setRecs(await listRecommendations())
    } catch (err) {
      setError(message(err))
    } finally {
      setLoading(false)
    }
  }, [email, ready])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    if (!recs) return
    const ids = new Set(recs.data.map(item => item.jobId))
    setSelected(current => {
      const next = new Set([...current].filter(id => ids.has(id)))
      return next.size === current.size ? current : next
    })
  }, [recs])

  async function generate() {
    setBusy(true)
    setError('')
    try {
      setRecs(await refreshRecommendations())
    } catch (err) {
      setError(message(err))
    } finally {
      setBusy(false)
    }
  }

  function toggleSelected(jobId: number) {
    setSelected(current => {
      const next = new Set(current)
      if (next.has(jobId)) next.delete(jobId)
      else next.add(jobId)
      return next
    })
    setAgentError('')
    setAgentNotice('')
  }

  function selectAll() {
    if (!recs) return
    setSelected(
      new Set(
        recs.data
          .filter(item => !queued.has(item.jobId))
          .map(item => item.jobId),
      ),
    )
  }

  function clearSelection() {
    setSelected(new Set())
  }

  async function startAgent() {
    const jobIds = [...selected].filter(id => !queued.has(id))
    if (!jobIds.length) return

    setAgentBusy(true)
    setAgentError('')
    setAgentNotice('')
    try {
      const result = await applyWithAgent(jobIds)
      setQueued(
        current =>
          new Set([...current, ...result.jobs.map(job => job.jobId)]),
      )
      setSelected(new Set())
      setAgentNotice(
        `Queued ${result.count} ${
          result.count === 1 ? 'job' : 'jobs'
        } for Talentry's auto-apply agent.`,
      )
    } catch (err) {
      setAgentError(message(err))
    } finally {
      setAgentBusy(false)
    }
  }

  if (!user) {
    return (
      <div>
        <PageHead
          title="Career coach"
          sub="Get job recommendations from your profile and CV."
        />
        <div className="panel">
          <h2>Sign in to get recommendations</h2>
          <p className="m" style={{ margin: '10px 0 20px' }}>
            We match open roles to your experience and save the list to your
            account.
          </p>
          <Link href="/?auth=login" className="btn" style={{ textDecoration: 'none' }}>
            Log in
          </Link>
        </div>
      </div>
    )
  }

  if (profile === undefined) {
    return (
      <div>
        <PageHead
          title="Career coach"
          sub="Get job recommendations from your profile and CV."
        />
        <p className="m">Loading your profile…</p>
      </div>
    )
  }

  if (!profile || !hasProfileDetails(profile)) {
    return (
      <div>
        <PageHead
          title="Career coach"
          sub="Get job recommendations from your profile and CV."
        />
        <div className="panel">
          <h2>Tell us about yourself first</h2>
          <p className="m" style={{ margin: '10px 0 20px' }}>
            Recommendations are built from your profile and CV. Add a title,
            location or a short summary and we can start matching you to roles.
          </p>
          <Link
            href="/profile"
            className="btn"
            style={{ textDecoration: 'none', maxWidth: 240 }}
          >
            Complete your profile
          </Link>
        </div>
      </div>
    )
  }

  const stale = recs ? staleReasons(recs.meta) : ''
  const selectableIds = recs
    ? recs.data.filter(item => !queued.has(item.jobId)).map(item => item.jobId)
    : []
  const allSelected =
    selectableIds.length > 0 && selectableIds.every(id => selected.has(id))

  return (
    <div>
      <PageHead
        title="Career coach"
        sub="Job recommendations picked for your profile and CV."
      />

      <section className="panel" style={{ marginBottom: 24 }}>
        <h2 style={{ fontSize: 24 }}>What we know about you</h2>
        <div className="dl">
          {profile.currentTitle ? (
            <div>Current title<b>{profile.currentTitle}</b></div>
          ) : null}
          {profile.yearsExperience !== null ? (
            <div>
              Experience
              <b>
                {profile.yearsExperience}{' '}
                {profile.yearsExperience === 1 ? 'year' : 'years'}
              </b>
            </div>
          ) : null}
          {profile.location ? (
            <div>Location<b>{profile.location}</b></div>
          ) : null}
          {profile.cvFilename ? (
            <div>CV<b>{profile.cvFilename}</b></div>
          ) : null}
        </div>
        {profile.headline ? (
          <p className="m" style={{ marginBottom: 8 }}>{profile.headline}</p>
        ) : null}
        {profile.summary ? (
          <p className="m" style={{ marginBottom: 8 }}>{profile.summary}</p>
        ) : null}
        <p className="m">
          We use these details and your CV to rank open roles. Update your{' '}
          <Link href="/profile">profile</Link> any time.
        </p>
      </section>

      {error ? (
        <section className="panel" style={{ marginBottom: 24 }}>
          <p className="perr" role="alert">{error}</p>
          <button
            className="btn coach-btn"
            style={{ marginTop: 16 }}
            onClick={() => void load()}
            disabled={loading || busy}
          >
            {loading ? 'Trying again…' : 'Try again'}
          </button>
        </section>
      ) : null}

      {loading && !recs ? <p className="m">Loading your recommendations…</p> : null}

      {agentNotice ? (
        <section className="panel rec-agent-notice" role="status">
          <p>{agentNotice}</p>
        </section>
      ) : null}

      {agentError ? (
        <section className="panel" style={{ marginBottom: 24 }}>
          <p className="perr" role="alert">{agentError}</p>
        </section>
      ) : null}

      {recs && stale && recs.data.length ? (
        <section className="panel rec-notice">
          <p>
            <b>These recommendations may be out of date.</b> Since we generated
            them, {stale}. Want a fresh set?
          </p>
          <button
            className="btn rec-refresh"
            onClick={() => void generate()}
            disabled={busy}
          >
            {busy ? 'Refreshing…' : 'Refresh recommendations'}
          </button>
        </section>
      ) : null}

      {recs && recs.data.length ? (
        <>
          <div className="rec-head">
            <div>
              <h2 style={{ fontSize: 28 }}>Recommended for you</h2>
              <p className="m">
                Apply manually, or pick roles and let the Talentry agent handle
                the applications.
              </p>
            </div>
            <div className="rec-head-actions">
              <button
                className="linkbtn"
                onClick={allSelected ? clearSelection : selectAll}
                disabled={agentBusy || !selectableIds.length}
              >
                {allSelected ? 'Clear selection' : 'Select all'}
              </button>
              <button
                className="linkbtn"
                onClick={() => void generate()}
                disabled={busy}
              >
                {busy ? 'Refreshing…' : 'Refresh'}
              </button>
            </div>
          </div>
          <div className="recs">
            {recs.data.map(item => (
              <RecommendationCard
                key={item.jobId}
                item={item}
                selected={selected.has(item.jobId)}
                queued={queued.has(item.jobId)}
                onToggle={toggleSelected}
              />
            ))}
          </div>

          {selected.size > 0 ? (
            <div className="agent-bar" role="region" aria-label="Talentry agent">
              <div className="agent-bar-info">
                <b>
                  {selected.size} {selected.size === 1 ? 'job' : 'jobs'} selected
                </b>
                <span>Talentry will apply to these roles for you.</span>
              </div>
              <div className="agent-bar-actions">
                <button
                  className="linkbtn"
                  onClick={clearSelection}
                  disabled={agentBusy}
                >
                  Clear
                </button>
                <button
                  className="btn agent-btn"
                  onClick={() => void startAgent()}
                  disabled={agentBusy}
                >
                  {agentBusy
                    ? 'Starting…'
                    : `Apply ${selected.size} ${
                        selected.size === 1 ? 'job' : 'jobs'
                      } with Talentry`}
                </button>
              </div>
            </div>
          ) : null}
        </>
      ) : null}

      {recs && !recs.data.length && !loading ? (
        <section className="panel">
          <h2>No recommendations yet</h2>
          <p className="m" style={{ margin: '10px 0 20px' }}>
            We could not find a match for your profile right now. Try again as
            new roles are added.
          </p>
          <button
            className="btn coach-btn"
            onClick={() => void generate()}
            disabled={busy}
          >
            {busy ? 'Generating…' : 'Generate my recommendations'}
          </button>
        </section>
      ) : null}

      {!recs && !loading && !error ? (
        <button
          className="btn coach-btn"
          onClick={() => void generate()}
          disabled={busy}
        >
          {busy ? 'Generating…' : 'Generate my recommendations'}
        </button>
      ) : null}
    </div>
  )
}
