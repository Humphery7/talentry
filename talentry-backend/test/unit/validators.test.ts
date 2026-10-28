import { describe, expect, it } from 'vitest';
import { HttpError } from '../../src/utils/http-error.js';
import { parseAgentApply } from '../../src/validators/agent-applications.validator.js';
import { parseApply } from '../../src/validators/applications.validator.js';
import {
  parseLogin,
  parseSignup,
} from '../../src/validators/auth.validator.js';
import { parseCandidateProfile } from '../../src/validators/candidate-profile.validator.js';
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

describe('parseCandidateProfile', () => {
  it('trims text and turns blank fields into null', () => {
    expect(
      parseCandidateProfile({
        currentTitle: ' Frontend Developer ',
        yearsExperience: 3,
        headline: '',
      }),
    ).toEqual({
      headline: null,
      currentTitle: 'Frontend Developer',
      yearsExperience: 3,
      location: null,
      summary: null,
    });
  });

  it('rejects a bad year count and overlong text', () => {
    expect(() =>
      parseCandidateProfile({ yearsExperience: 200, headline: 'x'.repeat(161) }),
    ).toThrow(HttpError);
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

describe('parseAgentApply', () => {
  it('accepts a non-empty list of positive integers and removes duplicates', () => {
    expect(parseAgentApply({ jobIds: [7, 9, 7] })).toEqual({
      jobIds: [7, 9],
    });
  });

  it('rejects missing, empty, non-integer and overlong lists', () => {
    expect(() => parseAgentApply({})).toThrow(HttpError);
    expect(() => parseAgentApply({ jobIds: [] })).toThrow(HttpError);
    expect(() => parseAgentApply({ jobIds: [7, '9'] })).toThrow(HttpError);
    expect(() => parseAgentApply({ jobIds: [0] })).toThrow(HttpError);
    expect(() =>
      parseAgentApply({ jobIds: Array.from({ length: 51 }, (_, i) => i + 1) }),
    ).toThrow(HttpError);
  });
});
