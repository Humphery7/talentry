import { HttpError } from '../utils/http-error.js';
import {
  requiredIntegerArray,
  requiredString,
  throwIfInvalid,
  type Input,
} from './rules.js';

export const DOCUMENT_KINDS = ['cv', 'cover_letter'] as const;
export type DocumentKind = (typeof DOCUMENT_KINDS)[number];

const UUID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function parseAgentApply(body: Input = {}): { jobIds: number[] } {
  const errors: string[] = [];
  const jobIds = requiredIntegerArray(body, 'jobIds', errors, {
    minItems: 1,
    maxItems: 50,
    min: 1,
  });
  throwIfInvalid(errors);
  return { jobIds };
}

export function parseApplicationId(raw: string): string {
  if (!UUID.test(raw)) throw new HttpError(400, 'Invalid application id.');
  return raw;
}

export function parseDocumentKind(raw: string): DocumentKind {
  if (!(DOCUMENT_KINDS as readonly string[]).includes(raw)) {
    throw new HttpError(400, 'Document must be cv or cover_letter.');
  }
  return raw as DocumentKind;
}

export function parseAnswers(body: Input = {}): {
  answers: { id: string; answer: string }[];
} {
  const list = body.answers;
  if (!Array.isArray(list) || list.length === 0 || list.length > 50) {
    throw new HttpError(400, 'answers must be a non-empty list.');
  }
  const answers = list.map((raw) => {
    const item = raw as Input;
    const errors: string[] = [];
    const id = requiredString(item, 'id', errors, {
      notEmpty: true,
      max: 40,
    });
    const answer = requiredString(item, 'answer', errors, { max: 4000 });
    if (!answer.trim()) errors.push('answer should not be empty');
    throwIfInvalid(errors);
    return { id, answer: answer.trim() };
  });
  return { answers };
}

export function parseFieldEdit(body: Input = {}): {
  key: string;
  value: string;
} {
  const errors: string[] = [];
  const key = requiredString(body, 'key', errors, {
    notEmpty: true,
    max: 200,
  });
  const value = requiredString(body, 'value', errors, { max: 6000 });
  throwIfInvalid(errors);
  return { key, value };
}

export function parseDocument(body: Input = {}): { content: string } {
  const errors: string[] = [];
  const content = requiredString(body, 'content', errors, {
    notEmpty: true,
    max: 20000,
  });
  if (!content.trim()) errors.push('content should not be empty');
  throwIfInvalid(errors);
  return { content };
}

export function parseQueueTop(body: Input = {}): { limit: number } {
  const errors: string[] = [];
  const limit = body.limit === undefined ? 5 : Number(body.limit);
  if (!Number.isInteger(limit) || limit < 1 || limit > 10) {
    errors.push('limit must be an integer between 1 and 10');
  }
  throwIfInvalid(errors);
  return { limit };
}

export function parseRetry(body: Input = {}): {
  confirmNotSubmitted: boolean;
} {
  if (
    body.confirmNotSubmitted !== undefined &&
    typeof body.confirmNotSubmitted !== 'boolean'
  ) {
    throw new HttpError(400, 'confirmNotSubmitted must be a boolean');
  }
  return { confirmNotSubmitted: body.confirmNotSubmitted === true };
}
