// Types + calls for job recommendations. The browser hits Next's
// /api/recommendations proxy, which forwards the JWT to the Express backend.
import { request } from './http'

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

export function listRecommendations() {
  return request<Recommendations>('/api/recommendations')
}

export function refreshRecommendations() {
  return request<Recommendations>('/api/recommendations', 'POST')
}
