// Entry point: `npm start`. Prepares the database, then starts listening.
import { createApp } from './app.js';
import { env } from './config/env.js';
import { runMigrations } from './db/migrate.js';
import { pool } from './db/pool.js';
import {
  startJobEmbeddingSchedule,
  stopJobEmbeddingSchedule,
} from './services/job-embedding-scheduler.js';

try {
  await runMigrations();
} catch (err) {
  console.error('Could not prepare the database:', err);
  process.exit(1);
}

startJobEmbeddingSchedule();

const server = createApp().listen(env.port, (err?: Error) => {
  if (err) {
    console.error('Could not start the server:', err);
    process.exit(1);
  }
  console.log(`Talentry API listening on http://localhost:${env.port}`);
});

// Ctrl+C / deploy restarts: stop accepting requests, then close DB connections.
function shutdown() {
  stopJobEmbeddingSchedule();
  server.close(() => {
    void pool.end().then(() => process.exit(0));
  });
}
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
