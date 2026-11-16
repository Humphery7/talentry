// Types + calls for the user's own Gemini API key. The key is write-only:
// the browser sends it once and only ever receives a masked hint back.
import { request } from './http'

export interface AiKeyStatus {
  configured: boolean
  hint: string | null
  updatedAt: string | null
}

export function getAiKeyStatus() {
  return request<AiKeyStatus>('/api/settings/ai')
}

export function saveAiKey(apiKey: string) {
  return request<AiKeyStatus>('/api/settings/ai', 'PUT', { apiKey })
}

export function removeAiKey() {
  return request<AiKeyStatus>('/api/settings/ai', 'DELETE')
}
