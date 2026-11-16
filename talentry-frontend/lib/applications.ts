'use client'
import { authHeaders } from './auth'
import { request } from './http'

export { ApiError } from './http'

export type Status =
  | 'queued'
  | 'in_progress'
  | 'needs_input'
  | 'pending_approval'
  | 'approved'
  | 'submitting'
  | 'awaiting_code'
  | 'submitted'
  | 'unconfirmed'
  | 'failed'
  | 'cancelled'

export interface Attention {
  id: string
  kind: 'question' | 'manual' | 'code'
  question: string
  label?: string | null
  why?: string | null
  context?: string | null
  options: string[] | null
  sensitive?: boolean
  answer: string | null
}

export interface CandidateCard {
  name: string | null
  email: string | null
  phone: string | null
  location: string | null
  linkedinUrl: string | null
  githubUrl: string | null
  websiteUrl: string | null
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
  result: {
    confirmation?: string
    manual?: boolean
    outcome?: string
  } | null
  screenshot: string | null
  candidate?: CandidateCard | null
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
  skipped: number[]
}

export const STATUS_TEXT: Record<Status, [string, string]> = {
  queued: ['Queued', 'Waiting for Talentry to pick this up.'],
  in_progress: ['Preparing', 'Talentry is working on the application form.'],
  needs_input: ['Needs you', 'All the open questions are on this page. Answer them once to continue.'],
  pending_approval: ['Ready for review', 'Check everything, then approve to submit.'],
  approved: ['Submitting soon', 'Approved. Talentry is about to submit.'],
  submitting: ['Submitting', 'Sending the application now.'],
  awaiting_code: ['Waiting for code', 'Talentry is holding the employer’s page open with your answers in it, while you enter the code they emailed.'],
  submitted: ['Submitted', 'The application was sent.'],
  unconfirmed: ['Check this one', 'Submission needs a quick check. The panel below says what to do.'],
  failed: ['Stopped', 'It could not finish. Your answers are kept, so Try again resumes.'],
  cancelled: ['Cancelled', 'You cancelled this application.'],
}

export const WORKING: Status[] = ['queued', 'in_progress', 'approved', 'submitting', 'awaiting_code']

export function call<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  return request<T>(`/api/agent-applications${path}`, method, body)
}

/**
 * The PDF a document was generated as, when one exists.
 *
 * A CV tailored from the candidate's own DOCX is rendered once, at generation
 * time, and that file is what the employer receives. Returning null means the
 * caller should fall back to printing the text.
 */
export async function documentPdf(
  id: string,
  kind: string,
  version: number,
): Promise<Blob | null> {
  const r = await fetch(
    `/api/agent-applications/${id}/documents/${kind}/pdf?version=${version}`,
    { headers: authHeaders(), cache: 'no-store' },
  )
  if (!r.ok) return null
  return r.blob()
}

export function applyWithAgent(jobIds: number[]) {
  return call<Batch>('', 'POST', { jobIds })
}

export function notificationCall<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  return request<T>(`/api/notifications${path}`, method, body)
}
