// Internal HTTP client for talentry-career. The Python service has no auth; the
// Express API is the only caller and always passes the trusted user id.
import { env } from '../config/env.js';
import { HttpError } from '../utils/http-error.js';

const CAREER_TIMEOUT_MS = 120_000;

async function request<T>(path: string, init: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${env.careerUrl}${path}`, {
      ...init,
      signal: AbortSignal.timeout(CAREER_TIMEOUT_MS),
    });
  } catch (err) {
    console.error('Career service request failed:', err);
    const timedOut = err instanceof Error && err.name === 'TimeoutError';
    throw new HttpError(
      timedOut ? 504 : 502,
      timedOut ? 'Career service timed out.' : 'Career service is unavailable.',
    );
  }

  const data = (await response.json().catch(() => null)) as {
    detail?: unknown;
  } | null;

  if (!response.ok) {
    const detail = data?.detail;
    const message =
      typeof detail === 'string' ? detail : 'Career service error.';
    throw new HttpError(response.status >= 500 ? 502 : response.status, message);
  }

  return data as T;
}

export function getCareer<T>(path: string): Promise<T> {
  return request<T>(path, { method: 'GET' });
}

export function postCareer<T>(path: string, payload: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}
