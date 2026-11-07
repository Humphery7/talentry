import { beforeEach, describe, expect, it, vi } from 'vitest';

const { query } = vi.hoisted(() => ({ query: vi.fn() }));

vi.mock('../../src/db/pool.js', () => ({
  pool: { query, connect: vi.fn() },
}));

import {
  answer,
  get,
  list,
  start,
} from '../../src/services/agent-applications.service.js';
import {
  parseAnswers,
  parseApplicationId,
  parseDocument,
  parseFieldEdit,
  parseQueueTop,
  parseRetry,
} from '../../src/validators/agent-applications.validator.js';

function jsonResponse(body: unknown, status = 202) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('agent applications service', () => {
  beforeEach(() => {
    query.mockReset();
    vi.unstubAllGlobals();
  });

  it('forwards the trusted user and job ids to the career service', async () => {
    const batch = {
      batchId: '9f1c7d5e-0000-4000-8000-000000000000',
      count: 2,
      jobs: [
        { jobId: 7, status: 'queued' },
        { jobId: 9, status: 'queued' },
      ],
    };
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(batch));
    vi.stubGlobal('fetch', fetchMock);

    const result = await start('user-1', [7, 9]);

    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8100/agent-applications',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: 'user-1', job_ids: [7, 9] }),
      }),
    );
    expect(result).toEqual(batch);
  });

  it('turns a career service outage into a 502', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('down')));
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    await expect(start('user-1', [7])).rejects.toMatchObject({ status: 502 });

    errorSpy.mockRestore();
  });

  it('lists applications from the database without screenshots', async () => {
    query.mockResolvedValueOnce({
      rows: [
        {
          id: 'app-1',
          jobId: '7',
          status: 'queued',
          jobTitle: 'Engineer',
          company: 'Acme',
          attentionCount: 0,
        },
      ],
    });

    const rows = await list('user-1');

    expect(query).toHaveBeenCalledWith(
      expect.stringContaining('FROM agent_applications'),
      ['user-1'],
    );
    expect(rows).toEqual([
      {
        id: 'app-1',
        jobId: 7,
        status: 'queued',
        jobTitle: 'Engineer',
        company: 'Acme',
        attentionCount: 0,
      },
    ]);
  });

  it('returns an empty list when the agent tables have not been created', async () => {
    query.mockRejectedValueOnce(
      Object.assign(new Error('missing'), { code: '42P01' }),
    );

    await expect(list('user-1')).resolves.toEqual([]);
  });

  it('adds ordered fields, grouped documents and activity to a detail', async () => {
    const detail = {
      id: 'app-1',
      jobId: 7,
      status: 'pending_approval',
      screenshot: 'base64',
      plan: {
        fields: {
          second: {
            label: 'Second',
            pos: 2,
            kind: 'text',
            required: true,
            value: 'b',
            source: 'profile',
            status: 'filled',
          },
          first: {
            label: 'First',
            pos: 1,
            kind: 'text',
            required: true,
            value: 'a',
            source: 'profile',
            status: 'filled',
          },
        },
      },
      attention: [],
      warnings: [],
      options: {},
      documents: [
        {
          kind: 'cv',
          version: 2,
          origin: 'generated',
          notes: [],
          content: 'new',
        },
        {
          kind: 'cv',
          version: 1,
          origin: 'original',
          notes: [],
          content: 'old',
        },
      ],
      result: null,
    };
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(detail, 200)),
    );
    query.mockResolvedValueOnce({
      rows: [
        {
          kind: 'ready',
          message: 'Ready for review.',
          createdAt: '2026-01-01T00:00:00.000Z',
        },
      ],
    });

    const result = await get('user-1', 'app-1');

    expect(result.fields.map((field) => field.key)).toEqual([
      'first',
      'second',
    ]);
    expect(result.documents.cv.version).toBe(2);
    expect(result.documents.cv.versions).toEqual([
      { version: 2, origin: 'generated' },
      { version: 1, origin: 'original' },
    ]);
    expect(result.events).toHaveLength(1);
    expect(result.screenshot).toBe('base64');
  });

  it('converts answer lists to the career dictionary shape', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(
        {
          id: 'app-1',
          status: 'queued',
          answered: 1,
        },
        200,
      ),
    );
    vi.stubGlobal('fetch', fetchMock);

    await answer('user-1', 'app-1', [{ id: 'q1', answer: 'Yes' }]);

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(
      'http://localhost:8100/agent-applications/app-1/answers?user_id=user-1',
    );
    expect(JSON.parse(init.body as string)).toEqual({
      answers: { q1: 'Yes' },
    });
  });
});

describe('agent applications validators', () => {
  it('validates ids and document kinds', () => {
    expect(parseApplicationId('123e4567-e89b-42d3-a456-426614174000')).toBe(
      '123e4567-e89b-42d3-a456-426614174000',
    );
    expect(() => parseApplicationId('not-a-uuid')).toThrow();
  });

  it('validates answers, field edits and document content', () => {
    expect(parseAnswers({ answers: [{ id: 'q1', answer: ' Yes ' }] })).toEqual({
      answers: [{ id: 'q1', answer: 'Yes' }],
    });
    expect(() => parseAnswers({ answers: [] })).toThrow();
    expect(parseFieldEdit({ key: 'phone', value: '' })).toEqual({
      key: 'phone',
      value: '',
    });
    expect(() => parseDocument({ content: '   ' })).toThrow();
  });

  it('validates queue and retry bodies', () => {
    expect(parseQueueTop({})).toEqual({ limit: 5 });
    expect(parseQueueTop({ limit: 10 })).toEqual({ limit: 10 });
    expect(() => parseQueueTop({ limit: 11 })).toThrow();
    expect(parseRetry({})).toEqual({ confirmNotSubmitted: false });
    expect(parseRetry({ confirmNotSubmitted: true })).toEqual({
      confirmNotSubmitted: true,
    });
  });
});
