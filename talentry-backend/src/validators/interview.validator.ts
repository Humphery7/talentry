import { HttpError } from '../utils/http-error.js';
import { requiredInteger, throwIfInvalid, type Input } from './rules.js';

export interface StartAttemptInput {
  jobId: number;
  newAttempt: boolean;
}

/** `POST /interview/attempts` */
export function parseStartAttempt(body: Input = {}): StartAttemptInput {
  const errors: string[] = [];
  const jobId = requiredInteger(body, 'jobId', errors, { min: 1 });

  let newAttempt = false;
  if (body.newAttempt !== undefined) {
    if (typeof body.newAttempt !== 'boolean') {
      errors.push('newAttempt must be a boolean');
    } else {
      newAttempt = body.newAttempt;
    }
  }

  throwIfInvalid(errors);
  return { jobId, newAttempt };
}

export interface InterviewAnswer {
  selectedOptionId?: string;
  text?: string;
  completed?: boolean;
}

/** The answer body for one question. The item type decides which field matters. */
export function parseAnswer(body: Input = {}): InterviewAnswer {
  const errors: string[] = [];
  const answer: InterviewAnswer = {};

  if (body.selectedOptionId !== undefined) {
    if (
      typeof body.selectedOptionId !== 'string' ||
      !/^[a-zA-Z0-9_-]{1,12}$/.test(body.selectedOptionId)
    ) {
      errors.push('selectedOptionId must be a short option id');
    } else {
      answer.selectedOptionId = body.selectedOptionId;
    }
  }

  if (body.text !== undefined) {
    if (typeof body.text !== 'string' || !body.text.trim()) {
      errors.push('text must be a non-empty string');
    } else if (body.text.length > 20_000) {
      errors.push('text must be shorter than or equal to 20000 characters');
    } else {
      answer.text = body.text;
    }
  }

  if (body.completed !== undefined) {
    if (typeof body.completed !== 'boolean') {
      errors.push('completed must be a boolean');
    } else {
      answer.completed = body.completed;
    }
  }

  if (
    answer.selectedOptionId === undefined &&
    answer.text === undefined &&
    answer.completed === undefined
  ) {
    errors.push('Provide selectedOptionId, text or completed.');
  }

  throwIfInvalid(errors);
  return answer;
}

export function parseAttemptId(raw: string): string {
  if (
    !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
      raw,
    )
  ) {
    throw new HttpError(400, 'Invalid interview attempt id.');
  }
  return raw;
}

export function parseItemId(raw: string): string {
  if (!/^[a-zA-Z0-9_-]{1,40}$/.test(raw)) {
    throw new HttpError(400, 'Invalid interview question id.');
  }
  return raw;
}

export function parseJobIdQuery(raw: unknown): number | undefined {
  if (raw === undefined || raw === '') return undefined;
  const value = Number(raw);
  if (!Number.isInteger(value) || value < 1) {
    throw new HttpError(400, 'jobId must be a positive integer.');
  }
  return value;
}
