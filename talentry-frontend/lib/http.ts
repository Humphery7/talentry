// One JSON request helper for every browser → Next proxy call. The status is
// kept on the error so a feature can tell "add your API key" (428) apart from
// a normal failure and show the right prompt.
import { authHeaders } from './auth'

export class ApiError extends Error {
  constructor(
    public messages: string[],
    public status: number,
  ) {
    super(messages.join(' '))
  }

  /** The server is asking for a Gemini API key before it can continue. */
  get needsAiKey(): boolean {
    return this.status === 428
  }
}

function errorMessages(data: unknown, status: number): string[] {
  const payload = data as { message?: unknown; error?: unknown } | null
  const raw = payload?.message ?? payload?.error ?? `Request failed (${status}).`
  return Array.isArray(raw) ? raw.map(String) : [String(raw)]
}

export async function request<T>(
  path: string,
  method = 'GET',
  body?: unknown,
): Promise<T> {
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
  if (!r.ok) throw new ApiError(errorMessages(data, r.status), r.status)
  return data as T
}
