# Talentry crawler

Background worker: read `data/boards.csv` → fetch ATS APIs → label jobs → embed jobs → write Neon Postgres.

**Read [`ARCHITECTURE.md`](ARCHITECTURE.md) first** — it explains the folders and the flow.

## Setup

```bash
cd crawler
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

Run this from `crawler/`; the shared package path is relative to it. Use
`requirements.txt` instead when deploying without test dependencies.

The first crawl downloads `sentence-transformers/all-MiniLM-L6-v2` (about 90 MB).
Cache `~/.cache/huggingface` in GitHub Actions so later runs reuse it.

Add your Neon connection string to `crawler/.env` (gitignored, never commit):

```bash
DATABASE_URL="postgresql://USER:PASSWORD@HOST/neondb?sslmode=require"
```

Without `DATABASE_URL` the crawler falls back to local SQLite (`output/jobs.db`,
plus `--db path/to.db` for tests). With it set, `run` / `stats` / `sample`
all hit Neon.

## Run

```bash
# One company
talentry-crawl run --limit 1 --ats greenhouse --company stripe

# Small batch across all supported ATS types
talentry-crawl run --limit 20

# Inspect
talentry-crawl stats
talentry-crawl sample --n 5
```

Run it again later: new jobs are added, known jobs are refreshed, and jobs that
disappeared from a career page are marked `closed` (never deleted).

## JSearch (an aggregator, not an ATS)

JSearch (OpenWebNinja) returns postings from Google for Jobs — LinkedIn, Indeed,
Glassdoor, Jooble — rather than one employer's board. It is the only source
with an API quota, so it is the only one that is budgeted:

* one row in `data/boards.csv` per saved search (`monitor_type=jsearch`,
  `monitor_config` = `{query, country, language, date_posted, num_pages}`);
* **one request = one page = up to 10 jobs.** `num_pages` maxes at 20, and
  every page costs a credit, so breadth (more queries) beats depth;
* the crawler runs daily but JSearch spends credits **once per ISO week**,
  rotating through the query list. `--jsearch-now` re-runs it in the same week;
* `JSEARCH_MONTHLY_REQUESTS` (default 180, out of a 200/month plan) is a hard
  local stop, counted in the `meta` table so a restart does not forget it;
* postings are deduped by JSearch's `job_uid` (stored as `jobs.external_id`),
  so five searches returning the same job store it once;
* a JSearch posting is also dropped **before it is inserted** when the
  employer's own board already has it: same company (names are normalised, so
  "Scribd, Inc." finds `scribd`), same title, same city, and **exactly one**
  open job matches. When several match — Accenture has 1,004 "Custom Software
  Engineer" rows in Pune — the copy is kept, because a duplicate is cheaper
  than a lost job. Employer boards are crawled before the aggregator pass for
  exactly this reason, so nothing is missed by a race;
* a JSearch board never closes jobs missing from today's page — the 30-day
  stale purge ages them out instead.

The run summary counts these as `dupes=` instead of `new=`, so the numbers
still add up.

There is deliberately **no byte cap** for JSearch: 180 requests/month is only
~15 MB of rows. Two guards protect the 1 GB database instead —
`JSEARCH_MAX_ROWS` (default 5000) and a pause once the database passes 90% of
`DB_STORAGE_LIMIT_MB` (default 1000).

Add the key to `crawler/.env` (gitignored) and as a repository secret:

```bash
JSEARCH_API_KEY="..."
```

## Test

```bash
pytest
```

The tests use fake API replies, so they run offline.

## Layout (short)

| Path | Role |
|------|------|
| `data/` | Input CSVs — *what* to crawl and what to label with |
| `output/` | `jobs.db` — *what we found* |
| `src/.../models/` | `Board` / `Job` / `Company` shapes |
| `src/.../config/` | Load the CSVs |
| `src/.../ats/` | One adapter per full-API ATS (Greenhouse, Ashby, Lever, Pinpoint, Recruitee, Gem, Personio, Deel, HireHive, Traffit, Manatal, BambooHR, HiBob, Recruiter.co.kr, TalentReef, Cornerstone, Beehire, SeamlessHiring, CNStaff, Pay-Net, Universia, Comeet, Jarvi, Keka, NowHiring, TurboHire, Amazon, Curately, 51job, Welcome to the Jungle, Woowa, Accenture, AlmaCareer, Beisen, Hireology, Wecruit, BrassRing, ByteDance, d.vinci, eArcu, Fenbi) plus the JSearch aggregator |
| `src/.../labeling/` | Seniority / occupation / technology labels |
| shared `packages/talentry_embeddings/` | Job/profile text builders and the sentence-transformer model |
| `src/.../storage/` | Database (SQLite fallback, Neon Postgres via `db.py` + `postgres.py`) |
| `src/.../pipeline/` | The crawl, step by step |
| `src/.../cli/` | `talentry-crawl` command |

## If you see "created by an older version"

`output/jobs.db` was made before jobs had a status and labels. Delete the file and run
again; it only holds crawled jobs, which are quick to re-fetch.
