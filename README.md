# Talentry

Talentry is a job board. We crawl company career pages, turn the listings into
something searchable, and put a site on top of it.

It's really three things living in one repo:

- **`crawler/`** — a Python worker that reads a list of companies and board URLs
  from a CSV, hits the ATS APIs behind them (Greenhouse, Ashby, Lever for now),
  tags each job by seniority/occupation/technologies, and writes everything to
  Postgres.
- **`talentry-backend/`** — the Express API. It reads the crawler's jobs, and
  owns the parts the crawler doesn't care about: user accounts and applications.
- **`talentry-frontend/`** — the Next.js site. Job search, job pages, companies,
  saved jobs, plus some CV/interview coaching screens that are still mostly
  mock-ups.

All three talk to the same database, so there's no syncing between services —
the crawler writes, the backend reads.

```
crawler (Python) ──writes──▶ Postgres ◀──reads/writes── backend (Express) ◀── frontend (Next.js)
```

## Running it locally

You'll need Node 20+ and Python 3.11+. Start with the crawler so the database
actually has something in it, then the backend, then the frontend.

### 1. Crawler

```bash
cd crawler
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# put your Postgres connection string in crawler/.env
echo 'DATABASE_URL="postgresql://user:pass@host/db?sslmode=require"' > .env

# crawl one company to check it works
talentry-crawl run --limit 1 --ats greenhouse --company stripe
```

Without `DATABASE_URL` it falls back to a local SQLite file, which is handy for
poking around offline. See `crawler/README.md` and `crawler/ARCHITECTURE.md` for
the rest.

### 2. Backend

```bash
cd talentry-backend
npm install
cp .env.example .env   # fill in DATABASE_URL and JWT_SECRET
npm run start:dev      # http://localhost:3001
```

To point the backend at the same database you just crawled into, reuse the
crawler's `DATABASE_URL`.

### 3. Frontend

```bash
cd talentry-frontend
npm install
npm run dev            # http://localhost:3000
```

By default the frontend expects the backend at `http://localhost:3001`. Change
it with `API_URL` if you're running the backend somewhere else.

## Tests

- Crawler: `pytest` from `crawler/` (runs offline against fake API responses).
- Backend: `npm test` for unit tests, and `TEST_DATABASE_URL=... npm run test:e2e`
  if you want the end-to-end ones against a real database.
- Frontend: no test suite yet.

## Data

`crawler/data/` holds the CSVs that drive everything — which companies to track,
which board each one lives on, and the word lists the labeler uses. Adding a
company is a CSV edit, not a code change. `crawler/data/README.md` explains the
files.

## Notes / known gaps

A few things you'll notice reading through it:

- The labeler is plain keyword matching. Good enough for now, not clever.
- Only three ATS providers are wired up, but `boards.csv` contains a lot more
  types (Workday, RSS, sitemaps…). Those rows are just skipped.
- The CV analyzer, career coach, and interview practice screens are UI-only.
- Saved jobs live in localStorage; there's no server-side saved-jobs endpoint.
- No sign in with Google yet, even though the config for it is sitting there.
