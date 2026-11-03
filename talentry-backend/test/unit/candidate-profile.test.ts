import { beforeEach, describe, expect, it, vi } from 'vitest';

const { query } = vi.hoisted(() => ({ query: vi.fn() }));

vi.mock('../../src/db/pool.js', () => ({ pool: { query } }));

import { save } from '../../src/services/candidate-profile.service.js';

describe('candidate profile service', () => {
  beforeEach(() => {
    query.mockReset();
    vi.unstubAllGlobals();
  });

  it('asks the career service to embed the saved profile', async () => {
    query.mockResolvedValueOnce({ rows: [{ userId: 'user-1' }] });
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ embedded: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const result = await save('user-1', {
      headline: 'Backend Engineer',
      currentTitle: null,
      yearsExperience: 3,
      location: 'Remote',
      summary: null,
    });

    expect(result).toEqual({ userId: 'user-1' });
    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/profiles/user-1/embedding',
      expect.objectContaining({ method: 'POST', body: '{}' }),
    );
  });
});
