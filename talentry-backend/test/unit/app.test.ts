import jwt from 'jsonwebtoken';
import request from 'supertest';
import { describe, expect, it } from 'vitest';
import { createApp } from '../../src/app.js';

const app = createApp();
const token = jwt.sign(
  { sub: 'user-1', email: 'a@example.com' },
  'test-secret',
  { expiresIn: '1h' },
);
const bearer = { Authorization: `Bearer ${token}` };

describe('basics', () => {
  it('GET / responds', async () => {
    const res = await request(app).get('/');
    expect(res.status).toBe(200);
    expect(res.text).toBe('Hello World!');
  });

  it('unknown routes return a 404 in the standard error shape', async () => {
    const res = await request(app).get('/nope');
    expect(res.status).toBe(404);
    expect(res.body).toEqual({
      message: 'Cannot GET /nope',
      error: 'Not Found',
      statusCode: 404,
    });
  });

  it('sends CORS headers', async () => {
    const res = await request(app)
      .get('/')
      .set('Origin', 'http://localhost:3000');
    expect(res.headers['access-control-allow-origin']).toBe('*');
  });

  it('rejects malformed JSON with 400', async () => {
    const res = await request(app)
      .post('/auth/login')
      .set('Content-Type', 'application/json')
      .send('{"email":');
    expect(res.status).toBe(400);
    expect(res.body.statusCode).toBe(400);
  });
});

describe('auth validation', () => {
  it('signup lists every invalid field', async () => {
    const res = await request(app)
      .post('/auth/signup')
      .send({ name: '', email: 'bad', password: 'short' });
    expect(res.status).toBe(400);
    expect(res.body.error).toBe('Bad Request');
    expect(res.body.message).toEqual([
      'name should not be empty',
      'email must be an email',
      'password must be longer than or equal to 8 characters',
    ]);
  });

  it('login with no body is a 400, not a crash', async () => {
    const res = await request(app).post('/auth/login');
    expect(res.status).toBe(400);
  });
});

describe('protected routes', () => {
  it.each([
    ['GET', '/auth/profile'],
    ['GET', '/applications'],
    ['POST', '/applications'],
    ['GET', '/interview/attempts'],
    ['POST', '/interview/attempts'],
    ['GET', '/interview/attempts/123e4567-e89b-42d3-a456-426614174000'],
    ['GET', '/interview/attempts/123e4567-e89b-42d3-a456-426614174000/feedback'],
    [
      'PUT',
      '/interview/attempts/123e4567-e89b-42d3-a456-426614174000/responses/i1',
    ],
  ] as const)('%s %s requires a token', async (method, path) => {
    const res = await request(app)[
      method.toLowerCase() as 'get' | 'post' | 'put'
    ](path);
    expect(res.status).toBe(401);
    expect(res.body).toEqual({
      message: 'Missing bearer token.',
      error: 'Unauthorized',
      statusCode: 401,
    });
  });

  it('rejects a bad token', async () => {
    const res = await request(app)
      .get('/auth/profile')
      .set('Authorization', 'Bearer garbage');
    expect(res.status).toBe(401);
    expect(res.body.message).toBe('Invalid or expired token.');
  });

  it('rejects an expired token', async () => {
    const expired = jwt.sign(
      { sub: 'u', email: 'a@example.com' },
      'test-secret',
      { expiresIn: -10 },
    );
    const res = await request(app)
      .get('/auth/profile')
      .set('Authorization', `Bearer ${expired}`);
    expect(res.status).toBe(401);
  });

  it('rejects a token signed with the wrong secret', async () => {
    const forged = jwt.sign(
      { sub: 'u', email: 'a@example.com' },
      'some-other-secret',
    );
    const res = await request(app)
      .get('/auth/profile')
      .set('Authorization', `Bearer ${forged}`);
    expect(res.status).toBe(401);
  });

  it('a valid token passes the guard and reaches body validation', async () => {
    const res = await request(app)
      .post('/applications')
      .set(bearer)
      .send({ jobId: 'nope' });
    expect(res.status).toBe(400);
    expect(res.body.message).toEqual(['jobId must be an integer number']);
  });

  it('validates interview requests before touching the database', async () => {
    const start = await request(app)
      .post('/interview/attempts')
      .set(bearer)
      .send({});
    expect(start.status).toBe(400);
    expect(start.body.message).toEqual(['jobId must be an integer number']);

    const answer = await request(app)
      .put(
        '/interview/attempts/123e4567-e89b-42d3-a456-426614174000/responses/i1',
      )
      .set(bearer)
      .send({});
    expect(answer.status).toBe(400);
    expect(answer.body.message).toEqual([
      'Provide selectedOptionId, text or completed.',
    ]);
  });
});

describe('query and param validation', () => {
  it.each([
    '/jobs?limit=0',
    '/jobs?limit=101',
    '/jobs?page=abc',
    '/jobs?lo=abc',
    '/jobs?status=bogus',
    '/jobs/abc',
    '/companies?limit=1000',
  ])('GET %s is a 400', async (url) => {
    const res = await request(app).get(url);
    expect(res.status).toBe(400);
    expect(res.body.error).toBe('Bad Request');
  });
});
