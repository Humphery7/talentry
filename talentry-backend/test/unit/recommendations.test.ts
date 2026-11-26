import { beforeEach, describe, expect, it, vi } from 'vitest';

const { query } = vi.hoisted(() => ({ query: vi.fn() }));

vi.mock('../../src/db/pool.js', () => ({ pool: { query } }));

import {
  get,
  normalizeFilters,
  refresh,
} from '../../src/services/recommendations.service.js';

const list = [
  {
    jobId: 7,
    rank: 1,
    score: 92,
    similarity: 0.81,
    reason: 'Strong frontend match.',
    title: 'Frontend Engineer',
    url: 'https://example.test/jobs/7',
    locations: ['Remote'],
    employmentType: 'Full time',
    workplaceType: 'Remote',
    seniority: 'senior',
    occupation: 'frontend-developer',
    company: 'Example',
  },
];

const metaRow = (generatedAt: string, embeddingUpdatedAt: string) => ({
  rows: [{ generatedAt: new Date(generatedAt), embeddingUpdatedAt: new Date(embeddingUpdatedAt) }],
});

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('recommendations service', () => {
  beforeEach(() => {
    query.mockReset();
    vi.unstubAllGlobals();
  });

  it('reads recommendations, saved filters and in-scope new-job counts', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(list));
    vi.stubGlobal('fetch', fetchMock);
    query
      .mockResolvedValueOnce({ rows: [{ filters: { lvl: ['Senior level'] } }] })
      .mockResolvedValueOnce(metaRow('2026-01-01T00:00:00.000Z', '2026-02-01T00:00:00.000Z'))
      .mockResolvedValueOnce({ rows: [{ count: 3 }] });

    const result = await get('user-1');

    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8100/recommendations/user-1',
      expect.objectContaining({ method: 'GET' }),
    );
    expect(result.data).toEqual(list);
    expect(result.filters).toEqual({ lvl: ['Senior level'] });
    expect(result.meta).toEqual({
      generatedAt: '2026-01-01T00:00:00.000Z',
      profileChanged: true,
      newJobs: 3,
    });
  });

  it('forwards new filters to the career service, then reads the list back', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ count: 1 }))
      .mockResolvedValueOnce(jsonResponse(list));
    vi.stubGlobal('fetch', fetchMock);
    query
      .mockResolvedValueOnce({ rows: [{ filters: { lvl: ['Senior level'] } }] })
      .mockResolvedValueOnce(metaRow('2026-01-02T00:00:00.000Z', '2026-01-01T00:00:00.000Z'))
      .mockResolvedValueOnce({ rows: [{ count: 0 }] });

    const result = await refresh('user-1', { lvl: ['Senior level'] });

    const [refreshUrl, refreshInit] = fetchMock.mock.calls[0] as [
      string,
      RequestInit,
    ];
    expect(refreshUrl).toBe('http://localhost:8100/recommendations/user-1');
    expect(refreshInit.method).toBe('POST');
    expect(refreshInit.body).toBe(
      JSON.stringify({ filters: { lvl: ['Senior level'] } }),
    );

    expect(fetchMock.mock.calls[1]?.[0]).toBe(
      'http://localhost:8100/recommendations/user-1',
    );
    expect(result.data).toEqual(list);
    expect(result.filters).toEqual({ lvl: ['Senior level'] });
    expect(result.meta.profileChanged).toBe(false);
  });

  it('keeps the saved scope when no filters are sent', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ count: 1 }))
      .mockResolvedValueOnce(jsonResponse(list));
    vi.stubGlobal('fetch', fetchMock);
    query
      .mockResolvedValueOnce({ rows: [{ filters: { types: ['contract'] } }] })
      .mockResolvedValueOnce(metaRow('2026-01-02T00:00:00.000Z', '2026-01-01T00:00:00.000Z'))
      .mockResolvedValueOnce({ rows: [{ count: 0 }] });

    await refresh('user-1');

    const [, refreshInit] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(refreshInit.body).toBe('{}');
  });

  it('falls back to empty metadata before the career service creates its table', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse([])));
    query.mockRejectedValue({ code: '42P01' });

    const result = await get('user-1');

    expect(result).toEqual({
      data: [],
      meta: { generatedAt: null, profileChanged: false, newJobs: 0 },
      filters: {},
    });
  });

  it('drops unknown keys and junk values from filters', () => {
    expect(
      normalizeFilters({
        loc: ['Europe', 'Europe', '  '],
        types: 'fulltime,contract',
        evil: ['x'],
        q: '  golang  ',
        lvl: 42,
      }),
    ).toEqual({
      loc: ['Europe'],
      types: ['fulltime', 'contract'],
      q: 'golang',
    });
  });
});
