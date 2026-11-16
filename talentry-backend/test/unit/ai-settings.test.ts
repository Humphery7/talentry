import { beforeEach, describe, expect, it, vi } from 'vitest';

const { query } = vi.hoisted(() => ({ query: vi.fn() }));

vi.mock('../../src/db/pool.js', () => ({
  pool: { query, connect: vi.fn() },
}));

import {
  decryptKey,
  encryptKey,
  get,
  remove,
  save,
} from '../../src/services/ai-settings.service.js';

const SAVED_AT = new Date('2026-11-16T10:00:00.000Z');

function savedRow(hint = '••••abcd') {
  return { rows: [{ key_hint: hint, updated_at: SAVED_AT }] };
}

describe('user Gemini key settings', () => {
  beforeEach(() => {
    query.mockReset();
    vi.unstubAllGlobals();
  });

  it('round-trips a key through the stored cipher', () => {
    const cipher = encryptKey('AIza-super-secret-key');

    expect(cipher).toMatch(/^v1:/);
    expect(cipher).not.toContain('super-secret');
    expect(decryptKey(cipher)).toBe('AIza-super-secret-key');
  });

  it('refuses a cipher that was tampered with', () => {
    const cipher = encryptKey('AIza-super-secret-key');
    const broken = cipher.slice(0, -4) + 'AAAA';

    expect(() => decryptKey(broken)).toThrow();
  });

  it('returns only a masked hint, never the key', async () => {
    query.mockResolvedValueOnce(savedRow());

    const status = await get('user-1');

    expect(status).toEqual({
      configured: true,
      hint: '••••abcd',
      updatedAt: SAVED_AT.toISOString(),
    });
    expect(JSON.stringify(status)).not.toContain('AIza');
  });

  it('checks the key with Google, then stores only the encrypted form', async () => {
    const fetchMock = vi.fn(async () => new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    query.mockResolvedValueOnce(savedRow());

    const status = await save('user-1', '  AIza-user-owned-key-1234  ');

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ];
    expect(url).toContain('generativelanguage.googleapis.com');
    expect((init.headers as Record<string, string>)['x-goog-api-key']).toBe(
      'AIza-user-owned-key-1234',
    );
    const params = query.mock.calls[0][1] as string[];
    expect(params[1]).toMatch(/^v1:/);
    expect(params[1]).not.toContain('user-owned-key');
    expect(params[2]).toBe('••••1234');
    expect(status.configured).toBe(true);
  });

  it('does not store a key Google rejects', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('{}', { status: 400 })),
    );

    await expect(save('user-1', 'AIza-not-a-real-key-0000')).rejects.toThrow(
      /did not accept/i,
    );
    expect(query).not.toHaveBeenCalled();
  });

  it('rejects an obvious non-key without calling Google', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    await expect(save('user-1', 'hello')).rejects.toThrow(/does not look/i);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(query).not.toHaveBeenCalled();
  });

  it('removes the stored key', async () => {
    query.mockResolvedValueOnce({ rows: [] });

    const status = await remove('user-1');

    expect(status).toEqual({
      configured: false,
      hint: null,
      updatedAt: null,
    });
    expect(query.mock.calls[0][0]).toContain('DELETE FROM user_ai_settings');
  });
});
