# Talentry

> **Status: local development only.** Talentry is not deployed. There is no
> hosted demo and no public API. To use it, clone the repo and run the services
> on your machine against a Postgres database.

Talentry is a job board plus an auto-apply assistant. We crawl company career
pages, turn the listings into something searchable, and put a site on top of it.

Five parts live in this repo:

- **`crawler/`** — a Python worker that reads a list of companies and board URLs
  from a CSV, hits the ATS APIs behind them (there is an adapter registry in
  `crawler/src/talentry_crawler/ats/`), tags each job by
  seniority/occupation/technologies, embeds it, and writes everything to
  Postgres.
- **`packages/talentry_embeddings/`** — the shared Python package that builds job
  and profile text and runs the MiniLM embedding model.
- **`talentry-backend/`** — the Express API. It reads the crawler's jobs and owns
  user accounts, profiles, applications, and notifications. It is also the only
  caller of `talentry-career`.
- **`talentry-career/`** — the FastAPI service that talks to Gemini for job
  recommendations, interview prep, and the auto-apply agent. It also embeds
  candidate profiles and runs the background worker that fills application
  forms in a real browser.
- **`talentry-frontend/`** — the Next.js site: job search, job pages, companies,
  saved jobs, profile/CV, career coach, interview practice, and applications.

All services share one Postgres database, so there is no syncing between them.
The crawler writes jobs and their vectors; the backend reads and writes user
data; the career service writes profile vectors, recommendations, interview
attempts, and agent applications.

```
crawler (Python) ──writes jobs + vectors──▶ Postgres ◀──reads/writes── backend (Express) ◀── frontend (Next.js)
                                                    │
                                                    └──server-side──▶ career (FastAPI) ──writes profile vectors──▶ Postgres
```

## Prerequisites

- **Node.js 20+** and npm.
- **Python 3.11+** (the crawler is also tested on 3.12).
- **PostgreSQL** with the [`pgvector`](https://github.com/pgvector/pgvector)
  extension. A free [Neon](https://neon.tech) database works out of the box; a
  local Postgres needs pgvector installed.
- **Google Chrome** for the auto-apply worker (Playwright drives it).
- Optional: **ngrok**, only if you use the root `npm run dev` script, because
  that script also starts a tunnel.

Every `.env` file is gitignored. Never commit database URLs, API keys, or
secrets.

## Quick start

There are two ways to run it: one command for the three backend-side services,
or each service in its own terminal. The frontend is always separate.

**First-time setup** (details in steps 1–5 below):

```bash
# Node dependencies: root scripts + backend + frontend
npm install
npm --prefix talentry-backend install
npm --prefix talentry-frontend install

# Python environments
cd talentry-career && python3 -m venv .venv \
  && .venv/bin/pip install -r requirements-dev.txt && cd ..
cd crawler && python3 -m venv .venv \
  && .venv/bin/pip install -r requirements-dev.txt && cd ..

# Fill in the .env files (see "Environment variables"), then crawl some jobs.
```

**Day-to-day:**

```bash
# Terminal 1: backend API + career service + auto-apply worker
npm run dev

# Terminal 2: the site
cd talentry-frontend && npm run dev
```

Open **http://localhost:3000**.

`npm run dev` starts:

| Process | Command | Port |
|---|---|---|
| API | `npm --prefix talentry-backend run start:dev` | 3001 |
| Career service | `uvicorn app:app --app-dir src --reload` with `AGENT_WORKER_ENABLED=0` | 8100 |
| Auto-apply worker | `python -m services.agent_applications.worker` | — |
| ngrok tunnel | `ngrok http 3001 --url https://unmarshalled-ghoulishly-evelyn.ngrok-free.dev` | 3001 |

The tunnel is only useful for Google sign-in from another origin. If you do not
have ngrok installed or configured, skip it and start the three processes
directly:

```bash
npx concurrently -k -n api,career,worker -c blue,magenta,yellow \
  "npm:dev:api" "npm:dev:career" "npm:dev:worker"
```

The existing `dev` script disables the career service's own worker supervisor
(`AGENT_WORKER_ENABLED=0`) and starts the worker separately. Run **one** worker
per database, not two.

## Step 1 — Database

1. Create a Postgres database. With Neon, copy the connection string and add
   `?sslmode=require` if it is not already there.
2. Put the same `DATABASE_URL` in all three files that need it:
   - `talentry-backend/.env`
   - `talentry-career/.env`
   - `crawler/.env` (only if you want the crawler to write to Postgres)
3. Start the backend once. It creates the shared schema and runs
   `CREATE EXTENSION IF NOT EXISTS vector` on boot. The career service creates
   its own tables when it starts.

A local Postgres must have pgvector available, and the database user must be
allowed to create extensions. On Neon this is already handled.

If the backend exits with `Could not prepare the database`, the URL is wrong or
the database cannot create the `vector` extension.

## Step 2 — Crawler

The crawler is what puts jobs in the database. Until it runs, the site has
nothing to show.

```bash
cd crawler
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

# crawler/.env
# DATABASE_URL="postgresql://USER:PASSWORD@HOST/neondb?sslmode=require"

# Crawl one company to check the setup
talentry-crawl run --limit 1 --ats greenhouse --company stripe

# Crawl a small batch across all supported ATS types
talentry-crawl run --limit 20

# Inspect what is in the database
talentry-crawl stats
talentry-crawl sample --n 5
```

The first run downloads `sentence-transformers/all-MiniLM-L6-v2` (about 90 MB)
and caches it in `~/.cache/huggingface`.

Run these commands from `crawler/`: the shared embedding package is installed
from a relative path.

Without `DATABASE_URL`, the crawler falls back to a local SQLite file at
`crawler/output/jobs.db`. That is useful for offline testing, but the backend
and frontend read Postgres — so set `DATABASE_URL` if you want the site to see
the jobs.

`crawler/data/` holds the CSVs that decide what to crawl and how to label it.
Adding a company is a CSV edit, not a code change. See `crawler/README.md` and
`crawler/ARCHITECTURE.md`.

There is also a scheduled GitHub Action at `.github/workflows/crawler.yml` that
runs `talentry-crawl run --concurrency 10` daily at 00:00 UTC using the
`DATABASE_URL` repository secret. It is not required for local development.

## Step 3 — Backend API

```bash
cd talentry-backend
npm install
cp .env.example .env
# Fill in DATABASE_URL and JWT_SECRET (and SESSION_SECRET if you use Google login)
npm run start:dev        # http://localhost:3001
```

On boot the API runs its migrations and starts a background cleanup job. It
runs about two minutes after boot, then daily. It trims old jobs, deletes
cancelled agent applications after 24 hours, and after 30 days keeps submitted
applications as a record but removes their generated documents and filled-in
details. Run it manually with `npm run db:cleanup`.

The API's routes are under `/auth`, `/jobs`, `/companies`, `/applications`,
`/agent-applications`, `/notifications`, `/candidate-profile`,
`/recommendations`, and `/interview`.

Google sign-in is optional. Leave the `GOOGLE_*` variables blank to disable it;
email/password login still works.

## Step 4 — Career service and auto-apply worker

```bash
cd talentry-career
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

# talentry-career/.env
# DATABASE_URL="postgresql://USER:PASSWORD@HOST/neondb?sslmode=require"
# GEMINI_API_KEY="..."

uvicorn app:app --app-dir src --reload --port 8100
```

The backend calls this service for profile embeddings, recommendations,
interview prep, and every auto-apply action. It needs `GEMINI_API_KEY`; without
it the AI features do not work.

The career service can start the auto-apply worker for you. If you run it
through `uvicorn` directly, that is the default (`AGENT_WORKER_ENABLED=1`). If
you start the worker separately — as the root `npm run dev` script does — set
`AGENT_WORKER_ENABLED=0` so you do not end up with two workers.

To run the worker separately:

```bash
cd talentry-career
PYTHONPATH=src .venv/bin/python -m services.agent_applications.worker
```

The worker needs Playwright's Chromium:

```bash
cd talentry-career
.venv/bin/playwright install chromium
```

On macOS 13, Playwright 1.64 has no bundled Chromium. Set
`PLAYWRIGHT_CHANNEL=chrome` in `talentry-career/.env` to use your installed
Chrome instead.

The worker opens the employer's page in a real browser, fills what it can from
your profile and CV, and pauses for you to answer missing questions or approve
the submission. It cannot solve CAPTCHAs: when one blocks submission, the
application pauses with an **Action needed** note, and you finish it on the
employer's site. The application page has a **Copy my details** button and a
**Download PDF** button for exactly that handoff.

## Step 5 — Frontend

```bash
cd talentry-frontend
npm install
npm run dev          # http://localhost:3000
```

By default it calls the backend at `http://localhost:3001` through Next.js route
handlers, so the browser never needs the API URL directly. Override it with
`API_URL` in `talentry-frontend/.env.local` if the backend is elsewhere.

## Environment variables

| Variable | Service | Required | Default / notes |
|---|---|---|---|
| `DATABASE_URL` | backend, career, crawler | backend & career | Same database for all three. Crawler falls back to SQLite when unset. |
| `JWT_SECRET` | backend | recommended | Signs login tokens. Generate with `node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"`. |
| `SESSION_SECRET` | backend | recommended | Signs the OAuth session cookie. Generate the same way. |
| `PORT` | backend | no | `3001` |
| `CAREER_API_URL` | backend | no | `http://localhost:8100` |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | backend | no | Enables Google sign-in. Leave blank to disable. |
| `OIDC_ISSUER` | backend | no | `https://accounts.google.com` |
| `REDIRECT_URL` | backend | no | `http://localhost:3001/auth/google/callback` — must match the Google console. |
| `FRONTEND_URL` | backend | no | `http://localhost:3000` |
| `GEMINI_API_KEY` | career | yes for AI features | Recommendations, interview prep, CV tailoring, cover letters. |
| `GEMINI_MODEL` | career | no | `gemini-3.5-flash-lite` |
| `PLAYWRIGHT_CHANNEL` | career | no | Set to `chrome` on macOS 13. |
| `PLAYWRIGHT_HEADLESS` | career | no | `true` |
| `PLAYWRIGHT_TIMEOUT_MS` | career | no | `30000` |
| `AGENT_WORKER_ENABLED` | career | no | `1`. Set to `0` when the worker runs as its own process. |
| `API_URL` | frontend | no | `http://localhost:3001` (server-side calls). |
| `NEXT_PUBLIC_API_URL` | frontend | no | Only used for client-side saved-job lookups. Leave blank to use the Next.js proxy. |

## Ports

| URL | Service |
|---|---|
| http://localhost:3000 | Frontend |
| http://localhost:3001 | Backend API |
| http://localhost:8100 | Career service (`/health` is a good check) |

## Tests

- **Crawler:** `pytest` from `crawler/` (runs offline against fake API replies).
- **Career:** `pytest` from `talentry-career/`.
- **Backend:** `npm test` for unit tests. For end-to-end tests against a real
  database, run `TEST_DATABASE_URL=... npm run test:e2e`.
- **Frontend:** typecheck with `npm run typecheck`; there is no test suite yet.

## Data

`crawler/data/` holds the CSVs that drive everything — which companies to track,
which board each one lives on, and the word lists the labeler uses. Adding a
company is a CSV edit, not a code change. `crawler/data/README.md` explains the
files.

## Notes and known gaps

- **Nothing is hosted.** There is no production deployment in this repo. The
  backend and frontend can be deployed separately, but that is not set up here.
- The labeler is plain keyword matching. Good enough for now, not clever.
- The crawler supports the ATS adapters listed in
  `crawler/src/talentry_crawler/ats/` (Greenhouse, Lever, Ashby, and many more).
  Any other `monitor_type` in `boards.csv` is skipped.
- Auto-apply jobs are queued by `talentry-career` in `agent_applications` and
  processed by the worker. Nothing is submitted until you approve it. Keep the
  worker running or queued jobs stay queued.
- The auto-apply worker cannot solve CAPTCHAs, and it cannot click suggestions
  in a custom autocomplete (for example Lever's "Current location"). In those
  cases it stops and asks you to finish the form yourself.
- Saved jobs live in `localStorage`; there is no server-side saved-jobs endpoint.
- Sign in with Google needs the `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` /
  `REDIRECT_URL` values in `talentry-backend/.env`.
- The database cleans itself up. Cancelled applications are deleted after 24
  hours. Submitted applications keep only a reference after 30 days; their
  generated CV, cover letter, and filled-in details are removed.

## Troubleshooting

- **`DATABASE_URL is not set`** — each service reads its own `.env`
  (`talentry-backend/.env`, `talentry-career/.env`, `crawler/.env`). They are
  not shared.
- **Backend exits immediately** — check the database URL and that pgvector is
  available. The error is printed before the process exits.
- **Frontend loads but API calls fail** — make sure the backend is on port 3001,
  or set `API_URL`.
- **The worker cannot start a browser** — run
  `.venv/bin/playwright install chromium`. On macOS 13 set
  `PLAYWRIGHT_CHANNEL=chrome`.
- **Jobs list is empty** — the crawler has not run against the same
  `DATABASE_URL` yet.
- **`npm run dev` dies at startup** — the ngrok step is the usual cause. Start
  the three processes directly with the `concurrently` command above.
