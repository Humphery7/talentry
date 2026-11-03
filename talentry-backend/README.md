# Talentry backend (Express API)

REST API over the same Neon Postgres database the crawler writes.

| Endpoint | Auth | Purpose |
| --- | --- | --- |
| `POST /auth/signup`, `POST /auth/login` | – | Create account / log in, returns `{ user, accessToken }` |
| `GET /auth/google/login`, `GET /auth/google/callback` | – | Sign in with Google (OpenID Connect) |
| `GET /auth/profile` | JWT | Current user |
| `GET /jobs`, `GET /jobs/:id` | – | Search (filters + paging) / one job |
| `GET /companies`, `GET /companies/:slug` | – | List / one company with its open jobs |
| `GET /candidate-profile`, `PUT /candidate-profile` | JWT | Read / save your optional career details |
| `PUT /candidate-profile/cv`, `GET /candidate-profile/cv` | JWT | Upload a PDF CV / download its extracted text |
| `POST /applications`, `GET /applications` | JWT | Apply to a job / list my applications |
| `POST /agent-applications` | JWT | Queue selected jobs for Talentry's auto-apply agent |
| `POST /agent-applications/queue-top` | JWT | Queue the best recommended jobs |
| `GET /agent-applications`, `GET /agent-applications/:id` | JWT | List / inspect auto-apply progress |
| `POST /agent-applications/:id/answers` | JWT | Answer questions that paused an application |
| `POST /agent-applications/:id/approve`, `/retry`, `/cancel`, `/resume`, `/manual-complete` | JWT | Review and control an application |
| `PUT /agent-applications/:id/fields`, `PUT /agent-applications/:id/documents/:kind` | JWT | Edit an answer or document before approval |
| `POST /agent-applications/:id/documents/:kind/regenerate` | JWT | Regenerate a CV or cover letter |
| `GET /notifications`, `POST /notifications/read` | JWT | Read / mark auto-apply notifications |
| `GET /recommendations`, `POST /recommendations/refresh` | JWT | Read / regenerate your job recommendations |

## Run

```bash
npm install
cp .env.example .env     # then fill in DATABASE_URL and JWT_SECRET
npm run start:dev        # http://localhost:3001, restarts on file changes
```

| Command | What it does |
| --- | --- |
| `npm start` | Run once (no file watching) |
| `npm run start:dev` | Run and restart on changes |
| `npm run build` then `npm run start:prod` | Compile to `dist/` and run the compiled JavaScript |
| `npm test` | Unit tests (no database needed) |
| `TEST_DATABASE_URL="postgresql://..." npm run test:e2e` | End-to-end tests against a real Postgres (see warning below) |
| `npm run typecheck` / `npm run lint` / `npm run format` | Type-check, lint, auto-format |

> **e2e warning:** these tests create and delete a throwaway user, so they only run when
> you pass `TEST_DATABASE_URL` explicitly. They never use the `DATABASE_URL` from `.env`.
> The database must already contain the crawler's `companies` and `jobs` tables.

## Environment (`.env`, gitignored)

```bash
DATABASE_URL="postgresql://USER:PASSWORD@HOST/neondb?sslmode=require"
JWT_SECRET="<long random string>"   # signs login tokens; changing it logs everyone out
PORT=3001
CAREER_API_URL="http://localhost:8000"  # internal Python service for recommendations, interview prep, and profile embeddings
```

Recommendations, interview prep, and agent applications call `talentry-career`
server-side; the browser never talks to it directly. The agent routes queue jobs
and proxy progress, answers, approval and retries to the career service. Document
and field edits are written to the shared `agent_applications` tables. Run that
service (and its auto-apply worker) separately and point `CAREER_API_URL` at it.

Google sign-in is optional. Fill these in to enable it (otherwise leave blank and the
endpoint just returns an error):

```bash
GOOGLE_CLIENT_ID="<from Google Cloud console>"
GOOGLE_CLIENT_SECRET="<from Google Cloud console>"
OIDC_ISSUER="https://accounts.google.com"
REDIRECT_URL="http://localhost:3001/auth/google/callback"  # must match the console exactly
FRONTEND_URL="http://localhost:3000"                       # where users land after login
SESSION_SECRET="<long random string>"                      # signs the short-lived OAuth session
```

On startup the server creates the tables and adds missing columns, including the
`vector` extension and the profile/job embedding columns. Saving a profile or uploading
a CV asks `talentry-career` to rebuild the profile vector. Job vectors are written by
the crawler in the same row as the job. Both use the shared Python embedding package
(`sentence-transformers/all-MiniLM-L6-v2`, 384 dimensions).

## Folder structure

```
src/
  server.ts          Entry point: run migrations, start listening, shut down cleanly
  app.ts             Builds the Express app: middleware + routes + error handling
  config/env.ts      Reads .env (DATABASE_URL, JWT_SECRET, PORT)
  db/
    pool.ts          The shared Postgres connection pool
    migrate.ts       Startup table/column creation
  routes/            URL + middleware + handler. One file per feature
  services/          Business logic and SQL. Know nothing about req/res
  validators/        Check request input; throw a 400 listing every problem
  middleware/
    auth.ts          requireAuth: verifies the Bearer JWT, sets req.user
    not-found.ts     404 for unknown URLs
    error-handler.ts Turns every thrown error into { message, error, statusCode }
  utils/http-error.ts  `throw new HttpError(404, 'Job not found.')`
test/
  unit/              Fast tests, no database
  e2e/               Full-stack tests against a real database
```

### How a request flows

`POST /applications` with `{ "jobId": 3 }`:

1. `routes/applications.routes.ts` matches it and runs `requireAuth`.
2. `middleware/auth.ts` verifies the token and sets `req.user`.
3. The route handler calls `parseApply(req.body)` to validate input.
4. `services/applications.service.ts` runs the SQL and returns the result.
5. The handler sends it with `res.status(201).json(...)`.

If anything throws (bad input, missing job, database down), Express skips straight to
`middleware/error-handler.ts`, which sends the error response. Express 5 forwards errors
from `async` functions automatically, so handlers need no try/catch.

### Adding an endpoint

1. Add the SQL/logic as a function in the feature's `services/*.service.ts`.
2. Add a validator in `validators/` if it takes input.
3. Add a route in `routes/*.routes.ts` whose handler calls the validator, then the service
   (add `requireAuth` to the route's middleware chain to protect it).
