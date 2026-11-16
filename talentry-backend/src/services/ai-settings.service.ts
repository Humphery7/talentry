// Each user's own Gemini API key. The key is encrypted before it is stored and
// is never returned to the browser; only a masked hint comes back.
import crypto from 'node:crypto';
import { env } from '../config/env.js';
import { pool } from '../db/pool.js';
import { HttpError } from '../utils/http-error.js';

const SALT = 'talentry-user-ai-key';
const VERSION = 'v1';

export interface AiKeyStatus {
  configured: boolean;
  hint: string | null;
  updatedAt: string | null;
}

interface Row {
  key_hint: string;
  updated_at: Date;
}

let cachedKey: Buffer | null = null;

function secretKey(): Buffer {
  if (cachedKey) return cachedKey;
  const secret = env.aiKeySecret;
  cachedKey = crypto.pbkdf2Sync(secret, SALT, 100_000, 32, 'sha256');
  return cachedKey;
}

/** AES-256-GCM envelope: `v1:iv:tag:ciphertext`, all base64url. */
export function encryptKey(plain: string): string {
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv('aes-256-gcm', secretKey(), iv);
  const body = Buffer.concat([cipher.update(plain, 'utf8'), cipher.final()]);
  const tag = cipher.getAuthTag();
  return [
    VERSION,
    iv.toString('base64url'),
    tag.toString('base64url'),
    body.toString('base64url'),
  ].join(':');
}

/** Kept so a future admin check can verify a stored key without exposing it. */
export function decryptKey(cipher: string): string {
  const [version, iv, tag, body] = cipher.split(':');
  if (version !== VERSION || !iv || !tag || !body) {
    throw new Error('Unknown AI key format.');
  }
  const decipher = crypto.createDecipheriv(
    'aes-256-gcm',
    secretKey(),
    Buffer.from(iv, 'base64url'),
  );
  decipher.setAuthTag(Buffer.from(tag, 'base64url'));
  return Buffer.concat([
    decipher.update(Buffer.from(body, 'base64url')),
    decipher.final(),
  ]).toString('utf8');
}

/**
 * Ask Google whether the key is real. `x-goog-api-key` keeps it out of the URL
 * (and therefore out of access logs). Only the status is inspected.
 */
async function verifyWithGoogle(apiKey: string): Promise<void> {
  let response: Response;
  try {
    response = await fetch(
      'https://generativelanguage.googleapis.com/v1beta/models',
      {
        headers: { 'x-goog-api-key': apiKey },
        signal: AbortSignal.timeout(15_000),
      },
    );
  } catch {
    throw new HttpError(
      502,
      'Could not reach Google to check that key. Try again.',
    );
  }
  if (response.ok) return;
  if (response.status === 400 || response.status === 401) {
    throw new HttpError(
      400,
      'Google did not accept that key. Check it and try again.',
    );
  }
  if (response.status === 403) {
    throw new HttpError(
      400,
      'That key is not allowed to use the Gemini API. Enable the API for it in Google AI Studio, then try again.',
    );
  }
  if (response.status === 429) {
    // The key is valid; it is just rate-limited. Saving it is still useful.
    return;
  }
  throw new HttpError(502, 'Google could not check that key right now.');
}

function statusFrom(row: Row | undefined): AiKeyStatus {
  return {
    configured: Boolean(row),
    hint: row?.key_hint ?? null,
    updatedAt: row ? row.updated_at.toISOString() : null,
  };
}

export async function get(userId: string): Promise<AiKeyStatus> {
  const { rows } = await pool.query<Row>(
    `SELECT key_hint, updated_at FROM user_ai_settings WHERE user_id = $1`,
    [userId],
  );
  return statusFrom(rows[0]);
}

export async function save(
  userId: string,
  raw: string,
): Promise<AiKeyStatus> {
  const apiKey = raw.trim();
  if (apiKey.length < 20 || apiKey.length > 200 || /\s/.test(apiKey)) {
    throw new HttpError(400, 'That does not look like a Gemini API key.');
  }

  await verifyWithGoogle(apiKey);

  const hint = `••••${apiKey.slice(-4)}`;
  const { rows } = await pool.query<Row>(
    `INSERT INTO user_ai_settings (user_id, gemini_key_cipher, key_hint, updated_at)
     VALUES ($1, $2, $3, now())
     ON CONFLICT (user_id) DO UPDATE
       SET gemini_key_cipher = EXCLUDED.gemini_key_cipher,
           key_hint = EXCLUDED.key_hint,
           updated_at = now()
     RETURNING key_hint, updated_at`,
    [userId, encryptKey(apiKey), hint],
  );
  return statusFrom(rows[0]);
}

export async function remove(userId: string): Promise<AiKeyStatus> {
  await pool.query(`DELETE FROM user_ai_settings WHERE user_id = $1`, [
    userId,
  ]);
  return { configured: false, hint: null, updatedAt: null };
}
