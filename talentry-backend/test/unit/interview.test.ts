import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  parseAnswer,
  parseAttemptId,
  parseItemId,
  parseJobIdQuery,
  parseStartAttempt,
} from '../../src/validators/interview.validator.js';

const { query } = vi.hoisted(() => ({ query: vi.fn() }));

vi.mock('../../src/db/pool.js', () => ({ pool: { query } }));

import {
  getAttempt,
  listAttempts,
  submitResponse,
} from '../../src/services/interview.service.js';

describe('interview validators', () => {
  it('parses a start request', () => {
    expect(parseStartAttempt({ jobId: 3 })).toEqual({
      jobId: 3,
      newAttempt: false,
    });
    expect(parseStartAttempt({ jobId: 3, newAttempt: true })).toEqual({
      jobId: 3,
      newAttempt: true,
    });
  });

  it('rejects invalid start requests', () => {
    expect(() => parseStartAttempt({ jobId: 0 })).toThrow();
    expect(() =>
      parseStartAttempt({ jobId: 1, newAttempt: 'yes' }),
    ).toThrow();
  });

  it('parses each answer shape and rejects an empty answer', () => {
    expect(parseAnswer({ selectedOptionId: 'a' })).toEqual({
      selectedOptionId: 'a',
    });
    expect(parseAnswer({ text: 'a real answer' })).toEqual({
      text: 'a real answer',
    });
    expect(parseAnswer({ completed: true })).toEqual({ completed: true });
    expect(() => parseAnswer({})).toThrow();
    expect(() => parseAnswer({ text: '   ' })).toThrow();
  });

  it('validates ids', () => {
    expect(parseAttemptId('123e4567-e89b-42d3-a456-426614174000')).toBe(
      '123e4567-e89b-42d3-a456-426614174000',
    );
    expect(() => parseAttemptId('not-a-uuid')).toThrow();
    expect(parseItemId('s1-q1')).toBe('s1-q1');
    expect(() => parseItemId('bad id')).toThrow();
    expect(parseJobIdQuery('4')).toBe(4);
    expect(parseJobIdQuery(undefined)).toBeUndefined();
    expect(() => parseJobIdQuery('0')).toThrow();
  });
});

describe('interview service reads', () => {
  beforeEach(() => {
    query.mockReset();
  });

  it('returns an empty list before the career service has created its tables', async () => {
    query.mockRejectedValueOnce({ code: '42P01' });
    await expect(listAttempts('user-1')).resolves.toEqual({ data: [] });
  });

  it('merges saved responses into the public assessment', async () => {
    const progress = {
      totalItems: 1,
      completedItems: 1,
      percent: 100,
      readiness: 80,
      sections: [{ id: 's1', completedItems: 1, totalItems: 1, percent: 100 }],
    };
    const assessment = {
      title: 'Prep',
      roleFamily: 'software-engineering',
      summary: 'Summary',
      estimatedMinutes: 10,
      sections: [
        {
          id: 's1',
          type: 'behavioural',
          title: 'Behavioural',
          priority: 'high',
          description: 'Description',
          estimatedMinutes: 10,
          items: [
            {
              id: 'i1',
              type: 'text_response',
              question: 'Tell me about yourself',
              instructions: null,
              topic: 'intro',
              difficulty: 'easy',
              relevance: 'high',
              estimatedMinutes: 5,
            },
          ],
        },
      ],
    };

    query
      .mockResolvedValueOnce({
        rows: [
          {
            id: 'attempt-1',
            jobId: '9',
            attemptNo: 1,
            status: 'completed',
            title: 'Prep',
            roleFamily: 'software-engineering',
            progress,
            createdAt: '2026-01-01T00:00:00.000Z',
            updatedAt: '2026-01-01T00:00:00.000Z',
            completedAt: '2026-01-01T00:00:00.000Z',
            assessment,
          },
        ],
      })
      .mockResolvedValueOnce({
        rows: [
          {
            itemId: 'i1',
            answer: { text: 'Hello' },
            score: 80,
            feedback: { score: 80, strengths: ['Clear'] },
            completed: true,
          },
        ],
      });

    const attempt = await getAttempt('user-1', 'attempt-1');

    expect(attempt.jobId).toBe(9);
    expect(attempt.assessment.sections[0].progress?.percent).toBe(100);
    expect(attempt.assessment.sections[0].items[0].completed).toBe(true);
    expect(attempt.assessment.sections[0].items[0].response?.score).toBe(80);
  });

  it('hides another user\u2019s attempt and missing tables', async () => {
    query.mockResolvedValueOnce({ rows: [] });
    await expect(getAttempt('user-1', 'attempt-1')).rejects.toMatchObject({
      status: 404,
    });

    query.mockRejectedValueOnce({ code: '42P01' });
    await expect(getAttempt('user-1', 'attempt-1')).rejects.toMatchObject({
      status: 404,
    });
  });
});

describe('interview answer submission', () => {
  beforeEach(() => {
    query.mockReset();
    vi.unstubAllGlobals();
  });

  it('does not call the career service for another user\u2019s attempt', async () => {
    query.mockResolvedValueOnce({ rowCount: 0 });
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    await expect(
      submitResponse('user-1', 'attempt-1', 'i1', { completed: true }),
    ).rejects.toMatchObject({ status: 404 });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('forwards the trusted user id to the career service', async () => {
    query.mockResolvedValueOnce({ rowCount: 1 });
    const payload = {
      itemId: 'i1',
      score: null,
      feedback: { completed: true },
      completed: true,
      progress: {
        totalItems: 1,
        completedItems: 1,
        percent: 100,
        readiness: null,
        sections: [],
      },
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const result = await submitResponse('user-1', 'attempt-1', 'i1', {
      completed: true,
    });

    expect(result.progress.percent).toBe(100);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('http://localhost:8000/interview/evaluate');
    expect(JSON.parse(init.body as string)).toMatchObject({
      user_id: 'user-1',
      attempt_id: 'attempt-1',
      item_id: 'i1',
    });
  });
});
