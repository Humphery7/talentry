// Builds the Express app. No database connection or port here, which keeps it
// easy to test: `createApp()` can be handed straight to supertest.
import cors from 'cors';
import express from 'express';
import { errorHandler } from './middleware/error-handler.js';
import { notFound } from './middleware/not-found.js';
import { routes } from './routes/index.js';

export function createApp() {
  const app = express();

  app.use(cors()); // allow any origin, same as before
  app.use(express.json());
  app.use(express.urlencoded({ extended: true }));

  app.use(routes);

  // These two must stay last: they catch what the routes didn't.
  app.use(notFound);
  app.use(errorHandler);

  return app;
}
