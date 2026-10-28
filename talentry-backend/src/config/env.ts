// Loads .env and exposes the settings the app needs, in one place.
import 'dotenv/config';

const databaseUrl = process.env.DATABASE_URL;
if (!databaseUrl) {
  throw new Error('DATABASE_URL is not set (talentry-backend/.env).');
}

if (!process.env.JWT_SECRET) {
  console.warn(
    'JWT_SECRET is not set - using an insecure development default.',
  );
}

if (!process.env.SESSION_SECRET) {
  console.warn(
    'SESSION_SECRET is not set - using an insecure development default.',
  );
}

export const env = {
  port: Number(process.env.PORT ?? 3001),
  databaseUrl,
  jwtSecret: process.env.JWT_SECRET ?? 'dev-secret-change-me',
  sessionSecret: process.env.SESSION_SECRET ?? 'dev-session-secret-change-me',
  // Internal Python service that generates and grades interview prep.
  careerUrl: (process.env.CAREER_API_URL ?? 'http://localhost:8000').replace(
    /\/$/,
    '',
  ),
  // How often to embed new/changed jobs. 0 disables the schedule.
  embedJobsIntervalMinutes: Number(
    process.env.EMBED_JOBS_INTERVAL_MINUTES ?? 15,
  ),
};

export const oidc_env = {
  issuer: process.env.OIDC_ISSUER ?? null,
  client: process.env.GOOGLE_CLIENT_ID,
  secret: process.env.GOOGLE_CLIENT_SECRET,
  // Where Google sends the browser back (this API's /auth/google/callback).
  redirect_url: process.env.REDIRECT_URL,
  // Where we send the browser once login succeeds.
  frontend_url: process.env.FRONTEND_URL ?? 'http://localhost:3000',
};
