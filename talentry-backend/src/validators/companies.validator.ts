import {
  optionalNumber,
  optionalString,
  throwIfInvalid,
  type Input,
} from './rules.js';

export interface CompaniesQuery {
  search?: string;
  industry?: string;
  page?: number;
  limit?: number;
}

export function parseCompaniesQuery(query: Input): CompaniesQuery {
  const errors: string[] = [];
  const parsed: CompaniesQuery = {
    search: optionalString(query, 'search', errors),
    industry: optionalString(query, 'industry', errors),
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
