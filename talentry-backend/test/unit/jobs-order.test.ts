import { beforeEach, describe, expect, it, vi } from 'vitest';

const { query } = vi.hoisted(() => ({ query: vi.fn() }));

vi.mock('../../src/db/pool.js', () => ({ pool: { query } }));

import { list } from '../../src/services/jobs.service.js';

/** `list` runs a count query, then the page query; only the page SQL matters. */
async function pageSql(params: Parameters<typeof list>[0]): Promise<string> {
  query
    .mockResolvedValueOnce({ rows: [{ total: 0 }] })
    .mockResolvedValueOnce({ rows: [] });
  await list(params);
  return query.mock.calls[1]?.[0] as string;
}

describe('jobs list ordering', () => {
  beforeEach(() => {
    query.mockReset();
  });

  it('defaults to newest posting date, with undated jobs last', async () => {
    const sql = await pageSql({});

    expect(sql).toContain('date_posted::timestamptz');
    expect(sql).toContain('pg_input_is_valid');
    expect(sql).toContain('DESC NULLS LAST');
    expect(sql).not.toContain('ORDER BY j.last_seen_at DESC');
  });

  it('sorts oldest postings first', async () => {
    const sql = await pageSql({ sort: 'oldest' });

    expect(sql).toContain('date_posted::timestamptz');
    expect(sql).toContain('ASC NULLS LAST');
  });

  it('keeps the old recently-confirmed order available', async () => {
    const sql = await pageSql({ sort: 'recent' });

    expect(sql).toContain('ORDER BY j.last_seen_at DESC');
    expect(sql).not.toContain('date_posted::timestamptz');
  });
});
