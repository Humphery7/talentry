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

/**
 * The saved scope for the career coach. Same keys as the jobs page, minus
 * salary. `loc` holds region slugs (`us`, `europe`, ...).
 */
export interface RecommendationFilters {
  loc?: string[]
  lvl?: string[]
  ind?: string[]
  sch?: string[]
  types?: string[]
  roles?: string[]
  q?: string
}

export interface Recommendations {
  data: Recommendation[]
  meta: RecommendationMeta
  /** `{}` means the coach is searching every open job. */
  filters: RecommendationFilters
}

export function listRecommendations() {
  return request<Recommendations>('/api/recommendations')
}

/** Omitting `filters` keeps the saved scope; `{}` clears it. */
export function refreshRecommendations(filters?: RecommendationFilters) {
  return request<Recommendations>(
    '/api/recommendations',
    'POST',
    filters === undefined ? undefined : { filters },
  )
}
