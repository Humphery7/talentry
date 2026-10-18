import { describe, expect, it } from 'vitest';
import { HttpError } from '../../src/utils/http-error.js';
import { parseApply } from '../../src/validators/applications.validator.js';
import {
  parseLogin,
  parseSignup,
} from '../../src/validators/auth.validator.js';
import { parseCompaniesQuery } from '../../src/validators/companies.validator.js';
import {
  parseJobId,
  parseJobsQuery,
} from '../../src/validators/jobs.validator.js';

describe('parseSignup', () => {
  it('returns only the known fields', () => {
    const input = parseSignup({
      name: 'Ada',
      email: 'ada@example.com',
      password: 'password1',
      role: 'admin',
    });
    expect(input).toEqual({
      name: 'Ada',
      email: 'ada@example.com',
      password: 'password1',
    });
  });

  it('throws an HttpError(400) listing the problems', () => {
    try {
      parseSignup({ name: 'x'.repeat(121), email: 'nope', password: 123 });
      expect.unreachable();
    } catch (err) {
      expect(err).toBeInstanceOf(HttpError);
      expect((err as HttpError).status).toBe(400);
      expect((err as HttpError).details).toEqual([
        'name must be shorter than or equal to 120 characters',
        'email must be an email',
        'password must be a string',
      ]);
    }
  });

  it('tolerates a missing body', () => {
    expect(() => parseSignup(undefined)).toThrow(HttpError);
  });
});

describe('parseLogin', () => {
  it('accepts valid credentials', () => {
    expect(parseLogin({ email: 'a@b.co', password: '12345678' })).toEqual({
      email: 'a@b.co',
      password: '12345678',
    });
  });
});

describe('parseJobsQuery', () => {
  it('turns numeric strings into numbers and keeps filters', () => {
    const q = parseJobsQuery({
      q: 'dev',
      lo: '50',
      hi: '90',
      page: '2',
      limit: '10',
      status: 'all',
      bogus: 'x',
    });
    expect(q).toMatchObject({
      q: 'dev',
      lo: 50,
      hi: 90,
      page: 2,
      limit: 10,
      status: 'all',
    });
    expect(q).not.toHaveProperty('bogus');
  });

  it('applies limits', () => {
    expect(() => parseJobsQuery({ limit: '101' })).toThrow(HttpError);
    expect(() => parseJobsQuery({ page: '0' })).toThrow(HttpError);
    expect(() => parseJobsQuery({ status: 'weird' })).toThrow(HttpError);
  });

  it('rejects repeated parameters (arrays)', () => {
    expect(() => parseJobsQuery({ q: ['a', 'b'] })).toThrow(HttpError);
  });
});

describe('parseJobId', () => {
  it('parses integers and rejects everything else', () => {
    expect(parseJobId('42')).toBe(42);
    expect(() => parseJobId('abc')).toThrow(HttpError);
    expect(() => parseJobId('4.2')).toThrow(HttpError);
  });
});

describe('parseCompaniesQuery / parseApply', () => {
  it('parses companies paging', () => {
    expect(parseCompaniesQuery({ search: 'acme', page: '3' })).toMatchObject({
      search: 'acme',
      page: 3,
    });
  });

  it('requires a positive integer jobId', () => {
    expect(parseApply({ jobId: 7 })).toEqual({ jobId: 7 });
    expect(() => parseApply({ jobId: 0 })).toThrow(HttpError);
    expect(() => parseApply({ jobId: '7' })).toThrow(HttpError);
    expect(() => parseApply({})).toThrow(HttpError);
  });
});
