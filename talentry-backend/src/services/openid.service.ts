import * as client from 'openid-client';
import { oidc_env } from '../config/env.js';

// Google is discovered (its endpoints fetched) once, the first time someone
// clicks "Sign in with Google". Doing it lazily instead of at import time means
// the server still starts when Google is not configured, e.g. in tests.
let cached: client.Configuration | undefined;

export async function getOidcConfig(): Promise<client.Configuration> {
  if (cached) return cached;

  if (!oidc_env.issuer || !oidc_env.client || !oidc_env.secret) {
    throw new Error(
      'Google login is not configured. Set OIDC_ISSUER, GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env.',
    );
  }

  cached = await client.discovery(
    new URL(oidc_env.issuer),
    oidc_env.client,
    oidc_env.secret,
  );
  return cached;
}
