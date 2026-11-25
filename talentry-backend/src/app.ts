// Builds the Express app. No database connection or port here, which keeps it
// easy to test: `createApp()` can be handed straight to supertest.
import cors from 'cors';
import express from 'express';
import session from 'express-session';
import { env } from './config/env.js';
import { errorHandler } from './middleware/error-handler.js';
import { notFound } from './middleware/not-found.js';
import { routes } from './routes/index.js';

export function createApp() {
  const app = express();

  // nginx terminates HTTPS and forwards plain HTTP to this process, adding
  // X-Forwarded-Proto. Without this line Express believes every request arrived
  // over http, so the "secure" session cookie below is never set and Google
  // login fails at the callback with "Login session expired".
  app.set('trust proxy', 1);

  app.use(cors()); // allow any origin, same as before
  app.use(express.json());
  app.use(express.urlencoded({ extended: true }));
  app.use(
    session({
      secret: env.sessionSecret,
      resave: false,
      saveUninitialized: false,
      cookie: {
        httpOnly: true,
        sameSite: 'lax', // must be lax, not strict, or the redirect back from the provider drops the cookie
        secure: process.env.NODE_ENV === 'production',
        maxAge: 1000 * 60 * 60 * 24 * 7,
      },
    }),
  );

  app.use(routes);

  // These two must stay last: they catch what the routes didn't.
  app.use(notFound);
  app.use(errorHandler);

  return app;
}
