import bcrypt from 'bcryptjs';
import jwt from 'jsonwebtoken';
import { env } from '../config/env.js';
import { pool } from '../db/pool.js';
import { HttpError } from '../utils/http-error.js';

export interface PublicUser {
  id: string;
  name: string;
  email: string;
}

/** Creates the login token the frontend stores and sends back as `Bearer <token>`. */
function signToken(user: PublicUser) {
  return jwt.sign({ sub: user.id, email: user.email }, env.jwtSecret, {
    expiresIn: '7d',
  });
}

export async function signup(name: string, email: string, password: string) {
  const normalized = email.trim().toLowerCase();
  const existing = await pool.query('SELECT id FROM users WHERE email = $1', [
    normalized,
  ]);
  if (existing.rowCount)
    throw new HttpError(409, 'Email is already registered.');

  const passwordHash = await bcrypt.hash(password, 10);
  const { rows } = await pool.query(
    'INSERT INTO users (name, email, password_hash) VALUES ($1, $2, $3) RETURNING id, name, email',
    [name.trim(), normalized, passwordHash],
  );
  const user = rows[0] as PublicUser;
  return { user, accessToken: signToken(user) };
}

export async function login(email: string, password: string) {
  const normalized = email.trim().toLowerCase();
  const { rows } = await pool.query(
    'SELECT id, name, email, password_hash FROM users WHERE email = $1',
    [normalized],
  );
  const row = rows[0] as
    (PublicUser & { password_hash: string | null }) | undefined;
  // password_hash is null for accounts created with Google, which have no password.
  if (
    !row?.password_hash ||
    !(await bcrypt.compare(password, row.password_hash))
  ) {
    throw new HttpError(401, 'Invalid email or password.');
  }
  const user: PublicUser = { id: row.id, name: row.name, email: row.email };
  return { user, accessToken: signToken(user) };
}

export interface GoogleProfile {
  name?: string;
  email?: string;
}

/**
 * Logs in a Google user, creating the account on first sight. Google has
 * already verified the email, so we match accounts on it. Returns the same
 * `{ user, accessToken }` shape as signup/login, so the frontend stores one
 * kind of session regardless of how someone signed in.
 */
export async function loginWithGoogle(profile: GoogleProfile) {
  const email = profile.email?.trim().toLowerCase();
  if (!email)
    throw new HttpError(400, 'Your Google account has no email address.');

  const existing = await pool.query(
    'SELECT id, name, email FROM users WHERE email = $1',
    [email],
  );
  if (existing.rowCount) {
    const user = existing.rows[0] as PublicUser;
    return { user, accessToken: signToken(user) };
  }


  const name = profile.name?.trim() || email.split('@')[0];
  const { rows } = await pool.query(
    'INSERT INTO users (name, email, password_hash) VALUES ($1, $2, NULL) RETURNING id, name, email',
    [name, email],
  );
  const user = rows[0] as PublicUser;
  return { user, accessToken: signToken(user) };
}

export async function getProfile(userId: string): Promise<PublicUser> {
  const { rows } = await pool.query(
    'SELECT id, name, email FROM users WHERE id = $1',
    [userId],
  );
  if (!rows.length) throw new HttpError(404, 'User not found.');
  return rows[0] as PublicUser;
}
