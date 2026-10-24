'use client'

import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { useCallback, useEffect, useState } from 'react'
import { loadSession } from '@/lib/auth'
import {
  type AnswerResult,
  type FeedbackShape,
  type InterviewAnswer,
  type InterviewAttempt,
  type InterviewItem,
  type InterviewSummary,
  getInterview,
  listInterviews,
  startInterview,
  submitInterviewAnswer,
} from '@/lib/interview'

function message(err: unknown): string {
  return err instanceof Error ? err.message : 'Something went wrong. Try again.'
}

function applyAnswer(
  attempt: InterviewAttempt,
  itemId: string,
  answer: InterviewAnswer,
  result: AnswerResult,
): InterviewAttempt {
  const sections = attempt.assessment.sections.map(section => ({
    ...section,
    progress:
      result.progress.sections.find(item => item.id === section.id) ??
      section.progress,
    items: section.items.map(item =>
      item.id === itemId
        ? {
            ...item,
            completed: result.completed,
            response: {
              answer: answer as Record<string, unknown>,
              score: result.score,
              feedback: result.feedback,
            },
          }
        : item,
    ),
  }))
  return {
    ...attempt,
    progress: result.progress,
    assessment: { ...attempt.assessment, sections },
  }
}

export default function InterviewPrep() {
  const params = useSearchParams()
  const jobId = Number(params.get('jobId') ?? 0)
  const [loggedIn, setLoggedIn] = useState<boolean | null>(null)
  const [attempt, setAttempt] = useState<InterviewAttempt | null>(null)
  const [attempts, setAttempts] = useState<InterviewSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState('')
  const [busyItem, setBusyItem] = useState<string | null>(null)

  useEffect(() => {
    setLoggedIn(Boolean(loadSession()))
  }, [])

  const load = useCallback(async () => {
    if (!Number.isInteger(jobId) || jobId < 1) {
      setError('Open interview prep from a job page.')
      setLoading(false)
      return
    }
    if (!loadSession()) {
      setLoading(false)
      return
    }

    setError('')
    setLoading(true)
    setGenerating(true)
    try {
      const current = await startInterview(jobId)
      setAttempt(current)
      setAttempts((await listInterviews(jobId)).data)
    } catch (err) {
      setError(message(err))
    } finally {
      setLoading(false)
      setGenerating(false)
    }
  }, [jobId])

  useEffect(() => {
    void load()
  }, [load])

  async function refreshList() {
    if (jobId > 0) setAttempts((await listInterviews(jobId)).data)
  }

  async function newAttempt() {
    setError('')
    setGenerating(true)
    try {
      setAttempt(await startInterview(jobId, true))
      await refreshList()
    } catch (err) {
      setError(message(err))
    } finally {
      setGenerating(false)
    }
  }

  async function openAttempt(id: string) {
    if (id === attempt?.id) return
    setError('')
    setLoading(true)
    try {
      setAttempt(await getInterview(id))
    } catch (err) {
      setError(message(err))
    } finally {
      setLoading(false)
    }
  }

  async function answer(item: InterviewItem, value: InterviewAnswer) {
    if (!attempt) return
    setError('')
    setBusyItem(item.id)
    try {
      const result = await submitInterviewAnswer(attempt.id, item.id, value)
      setAttempt(prev => (prev ? applyAnswer(prev, item.id, value, result) : prev))
    } catch (err) {
      setError(message(err))
    } finally {
      setBusyItem(null)
    }
  }

  if (loggedIn === false) {
    return (
      <div className="panel">
        <h2>Sign in to prepare for this role</h2>
        <p className="m" style={{ margin: '10px 0 20px' }}>
          Interview prep is saved to your account so you can come back to it.
        </p>
        <Link href="/?auth=login" className="btn" style={{ textDecoration: 'none' }}>
          Log in
        </Link>
      </div>
    )
  }

  if (generating) {
    return (
      <div className="panel" style={{ textAlign: 'center', padding: '64px 28px' }}>
        <h2>Building your interview prep</h2>
        <p className="m" style={{ marginTop: 10 }}>
          Matching questions to the job and your profile. This can take a few seconds.
        </p>
      </div>
    )
  }

  if (error && !attempt) {
    return (
      <div className="panel">
        <h2>Could not load interview prep</h2>
        <p className="m" style={{ margin: '10px 0 20px' }}>{error}</p>
        <button className="btn" onClick={() => void load()}>Try again</button>
      </div>
    )
  }

  if (!attempt) {
    return (
      <div className="panel">
        <h2>No interview prep yet</h2>
        <p className="m" style={{ margin: '10px 0 20px' }}>
          Open a job and choose Interview prep to generate one.
        </p>
        <Link href="/jobs" className="btn" style={{ textDecoration: 'none' }}>Browse jobs</Link>
      </div>
    )
  }

  const progress = attempt.progress

  return (
    <div>
      <div className="ph">
        <h1>{attempt.title}</h1>
        <p>
          {attempt.roleFamily.replace(/-/g, ' ')} · Attempt {attempt.attemptNo} ·{' '}
          {attempt.assessment.estimatedMinutes} min
        </p>
      </div>

      <section className="panel" style={{ marginBottom: 24 }}>
        <div className="iv-row">
          <div>
            <b style={{ fontSize: 24 }}>{progress.percent}%</b>
            <span className="m">
              {' '}complete · {progress.completedItems} of {progress.totalItems} activities
            </span>
          </div>
          {progress.percent === 100 && progress.readiness !== null ? (
            <div className="iv-score">Readiness {progress.readiness}/100</div>
          ) : null}
        </div>
        <div className="bar" style={{ marginTop: 12 }}>
          <i style={{ transform: `scaleX(${progress.percent / 100})` }} />
        </div>
        <p className="m" style={{ marginTop: 12 }}>{attempt.assessment.summary}</p>

        <div className="iv-actions">
          {attempts.length > 1 ? (
            <label className="iv-select">
              <span className="m">Attempt</span>
              <select
                className="f"
                value={attempt.id}
                onChange={event => void openAttempt(event.target.value)}
                disabled={loading || generating}
              >
                {attempts.map(item => (
                  <option key={item.id} value={item.id}>
                    {item.attemptNo} · {item.status} · {item.progress.percent}%
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <button
            className="btn iv-new"
            onClick={() => void newAttempt()}
            disabled={generating}
          >
            Start new attempt
          </button>
        </div>
        {error ? <p className="iv-error">{error}</p> : null}
      </section>

      {attempt.assessment.sections.map(section => {
        const percent = section.progress?.percent ?? 0
        return (
          <section key={section.id} className="panel" style={{ marginBottom: 24 }}>
            <div className="iv-row">
              <div>
                <h2 style={{ fontSize: 24 }}>{section.title}</h2>
                <p className="m" style={{ marginTop: 6 }}>{section.description}</p>
              </div>
              <span className="iv-pill">{percent}%</span>
            </div>
            <div className="bar" style={{ margin: '14px 0 4px' }}>
              <i style={{ transform: `scaleX(${percent / 100})` }} />
            </div>
            <p className="m" style={{ fontSize: 13 }}>
              {section.items.length} activities · {section.estimatedMinutes} min
            </p>

            <div style={{ display: 'grid', gap: 18, marginTop: 8 }}>
              {section.items.map(item => (
                <QuestionCard
                  key={item.id}
                  item={item}
                  busy={busyItem === item.id}
                  onAnswer={value => answer(item, value)}
                />
              ))}
            </div>
          </section>
        )
      })}
    </div>
  )
}

function QuestionCard({
  item,
  busy,
  onAnswer,
}: {
  item: InterviewItem
  busy: boolean
  onAnswer: (value: InterviewAnswer) => Promise<void>
}) {
  const [selected, setSelected] = useState('')
  const [text, setText] = useState('')

  useEffect(() => {
    const answer = item.response?.answer
    setSelected(
      answer && typeof answer.selectedOptionId === 'string'
        ? answer.selectedOptionId
        : '',
    )
    setText(answer && typeof answer.text === 'string' ? answer.text : '')
  }, [item.response])

  const feedback = item.response?.feedback ?? null
  const isMcq = item.type === 'multiple_choice'
  const isExternal = item.type === 'external_practice'

  return (
    <article className="iv-q">
      <div className="iv-tags">
        <span className="iv-tag">{item.type.replace(/_/g, ' ')}</span>
        <span className="iv-tag">{item.difficulty}</span>
        <span className="iv-tag">{item.estimatedMinutes} min</span>
        {item.completed ? <span className="iv-ok">done</span> : null}
      </div>
      <h3>{item.question}</h3>
      {item.instructions ? <p className="m">{item.instructions}</p> : null}

      {isMcq ? (
        <div style={{ display: 'grid', gap: 8, marginTop: 12 }}>
          {item.options?.map(option => (
            <label key={option.id} className="roleopt">
              <input
                type="radio"
                name={item.id}
                checked={selected === option.id}
                onChange={() => setSelected(option.id)}
                disabled={busy}
              />
              <span>{option.text}</span>
            </label>
          ))}
          <button
            className="btn iv-submit"
            disabled={busy || !selected}
            onClick={() => void onAnswer({ selectedOptionId: selected })}
          >
            {busy ? 'Saving…' : item.completed ? 'Update answer' : 'Submit answer'}
          </button>
        </div>
      ) : isExternal ? (
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 12 }}>
          {item.resource ? (
            <a
              className="btn iv-submit"
              href={item.resource.url}
              target="_blank"
              rel="noreferrer"
              style={{ textDecoration: 'none' }}
            >
              Open {item.resource.provider}
            </a>
          ) : null}
          <button
            className="btn iv-submit"
            disabled={busy}
            onClick={() => void onAnswer({ completed: !item.completed })}
          >
            {busy
              ? 'Saving…'
              : item.completed
                ? 'Mark not complete'
                : 'Mark complete'}
          </button>
        </div>
      ) : (
        <div style={{ marginTop: 12 }}>
          <textarea
            className="f"
            aria-label="Your answer"
            value={text}
            onChange={event => setText(event.target.value)}
            placeholder="Write your answer. Be specific and use examples."
            disabled={busy}
          />
          <button
            className="btn iv-submit"
            disabled={busy || !text.trim()}
            onClick={() => void onAnswer({ text })}
          >
            {busy ? 'Saving…' : item.completed ? 'Update answer' : 'Submit answer'}
          </button>
        </div>
      )}

      {feedback ? <Feedback feedback={feedback} score={item.response?.score ?? null} /> : null}
    </article>
  )
}

function Feedback({
  feedback,
  score,
}: {
  feedback: FeedbackShape
  score: number | null
}) {
  if (feedback.error) {
    return <div className="iv-feedback">{feedback.error}</div>
  }

  if (feedback.correct !== undefined) {
    return (
      <div className="iv-feedback">
        <b>{feedback.correct ? 'Correct' : 'Not quite'}</b>
        {feedback.explanation ? <p>{feedback.explanation}</p> : null}
      </div>
    )
  }

  if (feedback.completed !== undefined) {
    return (
      <div className="iv-feedback">
        {feedback.completed ? 'Marked complete.' : 'Marked not complete.'}
      </div>
    )
  }

  return (
    <div className="iv-feedback">
      {typeof score === 'number' ? <b>Score {score}/100</b> : null}
      {feedback.strengths?.length ? <List title="Strengths" items={feedback.strengths} /> : null}
      {feedback.weaknesses?.length ? <List title="Weaknesses" items={feedback.weaknesses} /> : null}
      {feedback.improvements?.length ? <List title="Improve" items={feedback.improvements} /> : null}
    </div>
  )
}

function List({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <b>{title}</b>
      <ul>
        {items.map((item, index) => (
          <li key={index}>{item}</li>
        ))}
      </ul>
    </div>
  )
}
