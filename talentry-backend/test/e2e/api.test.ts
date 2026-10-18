// Full-stack tests against a real Postgres (the crawler's `companies`/`jobs` tables
// must exist). Skipped unless TEST_DATABASE_URL is set. Creates one throwaway user
// and deletes it (and its applications) afterwards.
import request from 'supertest';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { createApp } from '../../src/app.js';
import { runMigrations } from '../../src/db/migrate.js';
import { pool } from '../../src/db/pool.js';

const email = `e2e-${Date.now()}@example.test`;
const password = 'correct-horse-battery';

describe.skipIf(!process.env.TEST_DATABASE_URL)('API (real database)', () => {
  const app = createApp();
  let token = '';
  let jobId: number | undefined;

  beforeAll(async () => {
    await runMigrations();
  });

  afterAll(async () => {
    await pool.query('DELETE FROM users WHERE email = $1', [email]);
    await pool.end();
  });

  it('signs up (201), refuses a duplicate (409), and logs in (200)', async () => {
    const signup = await request(app)
      .post('/auth/signup')
      .send({ name: 'E2E User', email, password });
    expect(signup.status).toBe(201);
    expect(signup.body.user).toMatchObject({ name: 'E2E User', email });
    expect(signup.body.accessToken).toBeTruthy();

    const dup = await request(app)
      .post('/auth/signup')
      .send({ name: 'E2E User', email, password });
    expect(dup.status).toBe(409);

    const login = await request(app)
      .post('/auth/login')
      .send({ email, password });
    expect(login.status).toBe(200);
    token = login.body.accessToken;

    const wrong = await request(app)
      .post('/auth/login')
      .send({ email, password: 'wrong-password' });
    expect(wrong.status).toBe(401);
  });

  it('returns the profile for a valid token', async () => {
    const res = await request(app)
      .get('/auth/profile')
      .set('Authorization', `Bearer ${token}`);
    expect(res.status).toBe(200);
    expect(res.body).toMatchObject({ email, name: 'E2E User' });
  });

  it('lists jobs with paging metadata and fetches one', async () => {
    const res = await request(app).get('/jobs?limit=2');
    expect(res.status).toBe(200);
    expect(res.body.meta).toMatchObject({ page: 1, limit: 2 });
    expect(res.body.data.length).toBeLessThanOrEqual(2);

    if (res.body.data.length) {
      jobId = res.body.data[0].id as number;
      const one = await request(app).get(`/jobs/${jobId}`);
      expect(one.status).toBe(200);
      expect(one.body.id).toBe(jobId);
      expect(one.body.company).toHaveProperty('slug');
    }
    expect((await request(app).get('/jobs/2147483647')).status).toBe(404);
  });

  it('lists companies and returns 404 for an unknown slug', async () => {
    const res = await request(app).get('/companies?limit=3');
    expect(res.status).toBe(200);
    expect(res.body.meta.limit).toBe(3);
    if (res.body.data.length) {
      const one = await request(app).get(`/companies/${res.body.data[0].slug}`);
      expect(one.status).toBe(200);
      expect(Array.isArray(one.body.jobs)).toBe(true);
    }
    expect(
      (await request(app).get('/companies/definitely-not-a-company')).status,
    ).toBe(404);
  });

  it('applies to a job once, treats a repeat as a duplicate, and lists applications', async (ctx) => {
    if (jobId === undefined) return ctx.skip();
    const auth = { Authorization: `Bearer ${token}` };

    const first = await request(app)
      .post('/applications')
      .set(auth)
      .send({ jobId });
    expect(first.status).toBe(201);
    expect(first.body.ok).toBe(true);
    expect(Number(first.body.jobId)).toBe(jobId); // Postgres returns BIGINT as a string

    const again = await request(app)
      .post('/applications')
      .set(auth)
      .send({ jobId });
    expect(again.status).toBe(201);
    expect(again.body).toEqual({ ok: true, jobId, duplicate: true });

    const missing = await request(app)
      .post('/applications')
      .set(auth)
      .send({ jobId: 2147483647 });
    expect(missing.status).toBe(409);

    const mine = await request(app).get('/applications').set(auth);
    expect(mine.status).toBe(200);
    expect(mine.body).toHaveLength(1);
    expect(mine.body[0]).toHaveProperty('title');
  });
});
