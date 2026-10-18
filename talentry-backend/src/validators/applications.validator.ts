import { requiredInteger, throwIfInvalid, type Input } from './rules.js';

export function parseApply(body: Input = {}): { jobId: number } {
  const errors: string[] = [];
  const jobId = requiredInteger(body, 'jobId', errors, { min: 1 });
  throwIfInvalid(errors);
  return { jobId };
}
