// Types + calls for job recommendations. The browser hits Next's
// /api/recommendations proxy, which forwards the JWT to the Express backend.
import { authHeaders } from './auth'

export interface Recommendation {
  jobId: number
  rank: number
  score: number
  similarity: number | null
  reason: string | null
  title: string
  url: string
  locations: string[]
  employmentType: string | null
  workplaceType: string | null
  seniority: string | null
  occupation: string | null
  company: string | null
}

export interface RecommendationMeta {
  generatedAt: string | null
  profileChanged: boolean
  newJobs: number
}

export interface Recommendations {
  data: Recommendation[]
  meta: RecommendationMeta
}

function errorMessage(data: unknown): string | null {
  if (!data || typeof data !== 'object') return null
  const message = (data as { message?: unknown }).message
  if (Array.isArray(message)) return message.join(', ')
  return typeof message === 'string' ? message : null
}

async function request(path: string, init?: RequestInit): Promise<Recommendations> {
  const r = await fetch(path, {
    ...init,
    headers: { ...authHeaders(), ...init?.headers },
    cache: 'no-store',
  })
  const data: unknown = await r.json().catch(() => null)
  if (!r.ok) {
    throw new Error(errorMessage(data) ?? `Request failed (${r.status}).`)
  }
  return data as Recommendations
}

export function listRecommendations() {
  return request('/api/recommendations')
}

export function refreshRecommendations() {
  return request('/api/recommendations', { method: 'POST' })
}
