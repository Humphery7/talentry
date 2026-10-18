import { HttpError } from '../utils/http-error.js';
import {
  optionalNumber,
  optionalOneOf,
  optionalString,
  throwIfInvalid,
  type Input,
} from './rules.js';

/** Mirrors the frontend URL params (q, loc, lvl, typ, ind, sch, co, lo, hi, types, sort, ids) + paging. */
export interface JobsQuery {
  q?: string;
  loc?: string;
  lvl?: string;
  typ?: string;
  ind?: string;
  sch?: string;
  co?: string;
  lo?: number;
  hi?: number;
  /** Comma-separated job types, e.g. `types=Full time,Contract`. */
  types?: string;
  sort?: string;
  /** Comma-separated numeric ids (saved-jobs lookup). */
  ids?: string;
  status?: 'open' | 'closed' | 'all';
  page?: number;
  limit?: number;
}

export function parseJobsQuery(query: Input): JobsQuery {
  const errors: string[] = [];
  const parsed: JobsQuery = {
    q: optionalString(query, 'q', errors),
    loc: optionalString(query, 'loc', errors),
    lvl: optionalString(query, 'lvl', errors),
    typ: optionalString(query, 'typ', errors),
    ind: optionalString(query, 'ind', errors),
    sch: optionalString(query, 'sch', errors),
    co: optionalString(query, 'co', errors),
    lo: optionalNumber(query, 'lo', errors),
    hi: optionalNumber(query, 'hi', errors),
    types: optionalString(query, 'types', errors),
    sort: optionalString(query, 'sort', errors),
    ids: optionalString(query, 'ids', errors),
    status: optionalOneOf(query, 'status', errors, ['open', 'closed', 'all']),
    page: optionalNumber(query, 'page', errors, { integer: true, min: 1 }),
    limit: optionalNumber(query, 'limit', errors, {
      integer: true,
      min: 1,
      max: 100,
    }),
  };
  throwIfInvalid(errors);
  return parsed;
}

/** Reads the `:id` in `/jobs/:id`. */
export function parseJobId(raw: string): number {
  if (!/^-?\d+$/.test(raw)) {
    throw new HttpError(400, 'Validation failed (numeric string is expected)');
  }
  return Number(raw);
}
