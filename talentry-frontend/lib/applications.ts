'use client'
import { authHeaders } from './auth'

export type Status =
  | 'queued'
  | 'in_progress'
  | 'needs_input'
  | 'pending_approval'
  | 'approved'
  | 'submitting'
  | 'submitted'
  | 'unconfirmed'
  | 'failed'
  | 'cancelled'

export interface Attention {
  id: string
  kind: 'question' | 'manual'
  question: string
  why?: string | null
  context?: string | null
  options: string[] | null
  sensitive?: boolean
  answer: string | null
}

export interface Field {
  key: string
  label: string
  kind: string
  required: boolean
  value: string
  source: string
  status: string
  options?: string[] | null
  note?: string | null
  sensitive?: boolean
  doc?: string | null
}

export interface DocumentVersion {
  version: number
  origin: string
}

export interface DocumentGroup {
  kind: string
  version: number
  content: string
  origin: string
  notes: string[]
  versions: DocumentVersion[]
}

export interface ApplicationEvent {
  kind: string
  message: string
  createdAt: string
}

export interface Detail {
  id: string
  jobId: number
  jobTitle: string | null
  company: string | null
  status: Status
  platform: string | null
  applyUrl: string | null
  error: string | null
  warnings: string[]
  attention: Attention[]
  fields: Field[]
  documents: { cv?: DocumentGroup; cover_letter?: DocumentGroup }
  events: ApplicationEvent[]
  result: { confirmation?: string; manual?: boolean } | null
  screenshot: string | null
  updatedAt: string
  approvedAt: string | null
  submittedAt: string | null
}

export interface Row {
  id: string
  jobId: number
  status: Status
  jobTitle: string | null
  company: string | null
  error: string | null
  attentionCount: number
  updatedAt: string
}

export interface Batch {
  batchId: string
  count: number
  jobs: { jobId: number; status: string }[]
}

export const STATUS_TEXT: Record<Status, [string, string]> = {
  queued: ['Queued', 'Waiting for Talentry to pick this up.'],
  in_progress: ['Preparing', 'Talentry is working on the application form.'],
  needs_input: ['Needs you', 'Paused until you answer or take a step.'],
  pending_approval: ['Ready for review', 'Check everything, then approve to submit.'],
  approved: ['Submitting soon', 'Approved. Talentry is about to submit.'],
  submitting: ['Submitting', 'Sending the application now.'],
  submitted: ['Submitted', 'The application was sent.'],
  unconfirmed: ['Check this one', 'We clicked submit but could not confirm it.'],
  failed: ['Failed', 'Something went wrong.'],
  cancelled: ['Cancelled', 'You cancelled this application.'],
}

export const WORKING: Status[] = ['queued', 'in_progress', 'approved', 'submitting']

export class ApiError extends Error {
  constructor(public messages: string[]) {
    super(messages.join(' '))
  }
}

async function request<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const r = await fetch(path, {
    method,
    headers: {
      ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
      ...authHeaders(),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: 'no-store',
  })
  const data: unknown = await r.json().catch(() => null)
  if (!r.ok) {
    const payload = data as { message?: unknown; error?: unknown } | null
    const raw = payload?.message ?? payload?.error ?? `Request failed (${r.status}).`
    throw new ApiError(Array.isArray(raw) ? raw.map(String) : [String(raw)])
  }
  return data as T
}

export function call<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  return request<T>(`/api/agent-applications${path}`, method, body)
}

export function applyWithAgent(jobIds: number[]) {
  return call<Batch>('', 'POST', { jobIds })
}

export function notificationCall<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  return request<T>(`/api/notifications${path}`, method, body)
}
