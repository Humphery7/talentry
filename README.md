# Talentry

Talentry is a job board. We crawl company career pages, turn the listings into
something searchable, and put a site on top of it.

It's four services plus one shared package, all living in one repo:

- **`crawler/`** — a Python worker that reads a list of companies and board URLs
  from a CSV, hits the ATS APIs behind them (Greenhouse, Ashby, Lever for now),
  tags each job by seniority/occupation/technologies, embeds it, and writes
  everything to Postgres.
- **`packages/talentry_embeddings/`** — the shared Python package that builds job
  and profile text and runs the MiniLM embedding model.
- **`talentry-backend/`** — the Express API. It reads the crawler's jobs, and
  owns the parts the crawler doesn't care about: user accounts, profiles, and
  applications.
- **`talentry-career/`** — the FastAPI service that talks to Gemini for job
  recommendations, interview prep, and the auto-apply agent. It also embeds
  candidate profiles. Only the backend calls it.
- **`talentry-frontend/`** — the Next.js site. Job search, job pages, companies,
  saved jobs, profile/CV, career coach, and interview practice.

All services share the same database, so there's no syncing between them — the
crawler writes jobs and their vectors, the backend reads and writes user data,
and the career service writes profile vectors, recommendations, interview
attempts, and agent applications.

```
crawler (Python) ──writes jobs + vectors──▶ Postgres ◀──reads/writes── backend (Express) ◀── frontend (Next.js)
                                                    │
                                                    └──server-side──▶ career (FastAPI) ──writes profile vectors──▶ Postgres
```

## Running it locally

You'll need Node 20+ and Python 3.11+. Start with the crawler so the database
actually has something in it, then the backend, then the frontend.

### 1. Crawler

```bash
cd crawler
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

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
crawler's `DATABASE_URL`. The backend creates the shared `users` and `jobs`
columns the career service relies on.

### 3. Career service

```bash
cd talentry-career
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

# .env needs DATABASE_URL and GEMINI_API_KEY
uvicorn app:app --app-dir src --reload --port 8000
```

The backend calls this service for profile embeddings, recommendations, interview
prep, and agent applications. Start it after the backend's first run so its schema
exists.

The auto-apply worker is a separate process. Run it alongside the API:

```bash
cd talentry-career
PYTHONPATH=src python -m services.agent_applications.worker
```

Playwright is included for the auto-apply workflow. Run
`playwright install chromium` once on platforms with a bundled build. On macOS 13
Playwright 1.64 has no bundled Chromium, so set
`PLAYWRIGHT_CHANNEL=chrome` in `talentry-career/.env` (or pass
`channel="chrome"`) to use the installed Chrome.

The reusable agent tools live in `talentry-career/src/services/browser/`:

```python
import asyncio

from services.browser import BrowserSession


async def main() -> None:
    async with BrowserSession() as session:
        tools = session.tools
        await tools.navigate("https://example.com")
        page = await tools.inspect_page()
        field = next(e for e in page.elements if e.name == "email")
        await tools.fill_field(field.id, "you@example.com")


asyncio.run(main())
```

Run this from `talentry-career` with `PYTHONPATH=src`.

`inspect_page` returns the visible text and interactive elements (inputs,
dropdowns, buttons, links, checkbox/radio labels, and custom ARIA controls) with
stable IDs. Actions include `fill_field`, `click_element`, `select_option`,
`set_checked`, `upload_file`, and `press_key`. Elements inside iframes and open
shadow roots are included.

### 4. Frontend

```bash
cd talentry-frontend
npm install
npm run dev            # http://localhost:3000
```

By default the frontend expects the backend at `http://localhost:3001`. Change
it with `API_URL` if you're running the backend somewhere else.

## Tests

- Crawler: `pytest` from `crawler/` (runs offline against fake API responses).
- Career: `pytest` from `talentry-career/`.
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
- Auto-apply jobs are queued by `talentry-career` in `agent_applications` and
  processed by the standalone worker. Keep the worker running or queued jobs
  will stay queued. Nothing is submitted until the user approves it.
- Saved jobs live in localStorage; there's no server-side saved-jobs endpoint.
- Sign in with Google is wired up (OpenID Connect) but needs the `GOOGLE_CLIENT_ID` /
  `GOOGLE_CLIENT_SECRET` / `REDIRECT_URL` values in `talentry-backend/.env`.
