// Types + calls for job-specific interview prep. The browser hits Next's
// /api/interview proxy, which forwards the JWT to the Express backend.
import { request } from './http'

export interface SectionProgress {
  id: string
  completedItems: number
  totalItems: number
  percent: number
}

export interface InterviewProgress {
  totalItems: number
  completedItems: number
  percent: number
  readiness: number | null
  sections: SectionProgress[]
}

export interface InterviewOption {
  id: string
  text: string
}

export interface InterviewResource {
  provider: string
  title: string
  url: string
}

export interface FeedbackShape {
  correct?: boolean
  correctOptionId?: string
  explanation?: string
  score?: number
  strengths?: string[]
  weaknesses?: string[]
  improvements?: string[]
  completed?: boolean
  error?: string
}

export interface InterviewResponse {
  answer: Record<string, unknown> | null
  score: number | null
  feedback: FeedbackShape | null
}

export interface InterviewItem {
  id: string
  type: string
  question: string
  instructions: string | null
  topic: string
  difficulty: string
  relevance: string
  estimatedMinutes: number
  options?: InterviewOption[]
  resource?: InterviewResource
  completed: boolean
  response: InterviewResponse | null
}

export interface InterviewSection {
  id: string
  type: string
  title: string
  priority: string
  description: string
  estimatedMinutes: number
  items: InterviewItem[]
  progress?: SectionProgress
}

export interface InterviewAssessment {
  title: string
  roleFamily: string
  summary: string
  estimatedMinutes: number
  sections: InterviewSection[]
}

export interface InterviewAttempt {
  id: string
  jobId: number
  attemptNo: number
  status: string
  title: string
  roleFamily: string
  progress: InterviewProgress
  createdAt: string
  updatedAt: string
  completedAt: string | null
  assessment: InterviewAssessment
}

export interface InterviewSummary {
  id: string
  jobId: number
  attemptNo: number
  status: string
  title: string
  roleFamily: string
  progress: InterviewProgress
  createdAt: string
  updatedAt: string
  completedAt: string | null
}

export interface InterviewAnswer {
  selectedOptionId?: string
  text?: string
  completed?: boolean
}

export interface AnswerResult {
  itemId: string
  score: number | null
  feedback: FeedbackShape
  completed: boolean
  progress: InterviewProgress
}

export function startInterview(jobId: number, newAttempt = false) {
  return request<InterviewAttempt>('/api/interview/attempts', 'POST', {
    jobId,
    newAttempt,
  })
}

export function listInterviews(jobId: number) {
  return request<{ data: InterviewSummary[] }>(
    `/api/interview/attempts?jobId=${jobId}`,
  )
}

export function getInterview(attemptId: string) {
  return request<InterviewAttempt>(`/api/interview/attempts/${attemptId}`)
}

export function submitInterviewAnswer(
  attemptId: string,
  itemId: string,
  answer: InterviewAnswer,
) {
  return request<AnswerResult>(
    `/api/interview/attempts/${attemptId}/responses/${encodeURIComponent(itemId)}`,
    'PUT',
    answer,
  )
}

export function getInterviewFeedback(attemptId: string) {
  return request<{
    progress: InterviewProgress
    items: Array<{
      itemId: string
      question: string
      topic: string
      type: string
      score: number | null
      feedback: FeedbackShape | null
      completed: boolean
    }>
  }>(`/api/interview/attempts/${attemptId}/feedback`)
}
