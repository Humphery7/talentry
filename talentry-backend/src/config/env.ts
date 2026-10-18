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

export const env = {
  port: Number(process.env.PORT ?? 3001),
  databaseUrl,
  jwtSecret: process.env.JWT_SECRET ?? 'dev-secret-change-me',
};
