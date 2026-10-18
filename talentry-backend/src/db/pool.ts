// One shared Postgres connection pool (same Neon database the crawler writes).
import { Pool } from 'pg';
import { env } from '../config/env.js';

export const pool = new Pool({
  connectionString: env.databaseUrl,
  // Neon requires TLS; system CAs validate it, this just forces it on.
  ssl: { rejectUnauthorized: false },
  max: 5,
});

// Without this, an idle connection dropped by the server would crash the process.
pool.on('error', (err) => {
  console.error('Unexpected Postgres pool error:', err.message);
});
