# Talentry crawler

Background worker: read `data/boards.csv` → fetch ATS APIs → label jobs → write Neon Postgres.

**Read [`ARCHITECTURE.md`](ARCHITECTURE.md) first** — it explains the folders and the flow.

## Setup

```bash
cd crawler
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

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
| `src/.../ats/` | One adapter per full-API ATS (Greenhouse, Ashby, Lever, Pinpoint, Recruitee, Gem, Personio, Deel, HireHive, Traffit, Manatal, BambooHR, HiBob, Recruiter.co.kr, TalentReef, Cornerstone, Beehire, SeamlessHiring, CNStaff, Pay-Net, Universia, Comeet, Jarvi, Keka, NowHiring, TurboHire, Amazon, Curately, 51job, Welcome to the Jungle, Woowa, Accenture, AlmaCareer, Beisen, Hireology, Wecruit, BrassRing, ByteDance, d.vinci, eArcu, Fenbi) |
| `src/.../labeling/` | Seniority / occupation / technology labels |
| `src/.../storage/` | Database (SQLite fallback, Neon Postgres via `db.py` + `postgres.py`) |
| `src/.../pipeline/` | The crawl, step by step |
| `src/.../cli/` | `talentry-crawl` command |

## If you see "created by an older version"

`output/jobs.db` was made before jobs had a status and labels. Delete the file and run
again; it only holds crawled jobs, which are quick to re-fetch.
