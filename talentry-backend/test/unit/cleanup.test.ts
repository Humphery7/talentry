import { beforeEach, describe, expect, it, vi } from 'vitest';

const { query, connect } = vi.hoisted(() => ({
  query: vi.fn(),
  connect: vi.fn(),
}));

vi.mock('../../src/db/pool.js', () => ({
  pool: { query, connect },
}));

import {
  rewriteFits,
  runCleanup,
  shouldRewriteJobs,
} from '../../src/db/cleanup.js';

const MB = 1024 * 1024;
const DAY = 24 * 60 * 60 * 1000;

describe('shouldRewriteJobs', () => {
  const baseline = {
    baselineBytes: 200 * MB,
    baselineRows: 100_000,
    lastRewriteAt: new Date(Date.now() - 30 * DAY),
  };

  it('rewrites a large table even before it has a baseline', () => {
    expect(
      shouldRewriteJobs({
        sizeBytes: 300 * MB,
        rows: 100_000,
        baselineBytes: null,
        baselineRows: null,
        lastRewriteAt: null,
      }),
    ).toBe(true);
  });

  it('leaves a small table alone', () => {
    expect(
      shouldRewriteJobs({
        sizeBytes: 50 * MB,
        rows: 1_000,
        baselineBytes: null,
        baselineRows: null,
        lastRewriteAt: null,
      }),
    ).toBe(false);
  });

  it('ignores growth that is just more jobs', () => {
    // 10% more rows at the same density is not bloat.
    expect(
      shouldRewriteJobs({
        sizeBytes: 220 * MB,
        rows: 110_000,
        ...baseline,
      }),
    ).toBe(false);
  });

  it('ignores bloat below the growth threshold', () => {
    expect(
      shouldRewriteJobs({
        sizeBytes: 300 * MB, // 80 MB above the per-row expectation
        rows: 110_000,
        ...baseline,
      }),
    ).toBe(false);
  });

  it('rewrites once per-row growth is worth the lock', () => {
    expect(
      shouldRewriteJobs({
        sizeBytes: 330 * MB, // 110 MB above expectation, 1.5x the baseline
        rows: 110_000,
        ...baseline,
      }),
    ).toBe(true);
  });

  it('waits out the minimum interval between rewrites', () => {
    expect(
      shouldRewriteJobs({
        sizeBytes: 900 * MB,
        rows: 110_000,
        baselineBytes: 200 * MB,
        baselineRows: 100_000,
        lastRewriteAt: new Date(Date.now() - DAY),
      }),
    ).toBe(false);
  });

  it('does nothing on an empty table', () => {
    expect(
      shouldRewriteJobs({
        sizeBytes: 0,
        rows: 0,
        baselineBytes: null,
        baselineRows: null,
        lastRewriteAt: null,
      }),
    ).toBe(false);
  });
});

describe('rewriteFits', () => {
  it('refuses a rewrite that would cross the storage limit', () => {
    // The real numbers that started this: 718 MB database, 703 MB jobs table.
    expect(rewriteFits(718 * MB, 703 * MB)).toBe(false);
  });

  it('allows a rewrite with plenty of room', () => {
    expect(rewriteFits(400 * MB, 300 * MB)).toBe(true);
  });

  it('refuses when the size could not be measured', () => {
    expect(rewriteFits(0, 300 * MB)).toBe(false);
  });
});

describe('runCleanup', () => {
  beforeEach(() => {
    query.mockReset();
    connect.mockReset();
    query.mockResolvedValue({ rows: [{ latest: null }], rowCount: 0 });
  });

  it('does not rewrite the table when the dry measurements say it is small', async () => {
    query.mockResolvedValue({
      rows: [{ latest: null, bytes: String(20 * MB), rows: '500' }],
      rowCount: 0,
    });

    await runCleanup();

    expect(
      query.mock.calls.some((call) =>
        String(call[0]).includes('VACUUM (FULL'),
      ),
    ).toBe(false);
  });
});
