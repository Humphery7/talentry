# Crawler architecture

One job: **read which boards to check → fetch their jobs → label them → save them.**

Nothing else lives in this package. No website, no search index, no Redis.

## The flow (left → right)

```
 data/*.csv        ats            labeling         storage
┌──────────┐    ┌──────────┐    ┌───────────┐    ┌───────────┐
│  config  │ ─► │   ats    │ ─► │ labeling  │ ─► │  storage  │ ─► output/jobs.db
│          │    │          │    │           │    │           │
│ boards   │    │greenhouse│    │ seniority │    │ companies │
│ companies│    │pinpoint  │    │ occupation│    │ jobs      │
│ labels   │    │  ...     │    │ tech      │    │ (open /   │
└──────────┘    └──────────┘    └───────────┘    │  closed)  │
      ▲                                          └───────────┘
      │               pipeline/crawl.py runs these steps in order
      └──────────────  cli (how a human starts it)  ──────────────
```

| Step | Folder | Question it answers |
|------|--------|---------------------|
| 1 | `config/` | *Which* boards do we crawl, and *what words* do we label with? |
| 2 | `ats/` | *How* do we talk to each ATS API? (one file per provider) |
| 3 | `labeling/` | *What kind* of job is this? (seniority, occupation, technologies) |
| 4 | `storage/` | *Where* do jobs live, and which ones have disappeared? |
| — | `pipeline/` | *In what order* do those steps run? |
| — | `cli/` | *How* does a human start / inspect a run? |
| — | `models/` | The shared shapes (`Board`, `Job`, `Company`) every layer passes around |

## Folder map

```
crawler/
├── ARCHITECTURE.md          ← you are here
├── README.md                ← how to install & run
├── data/                    ← input: CSVs that say WHAT to crawl and what to label with
├── output/                  ← output: jobs.db (not committed)
├── tests/                   ← run with: pytest
└── src/talentry_crawler/
    ├── models/              ← Board, Job, Company, LabelDictionaries  (no logic)
    ├── config/              ← boards.py, companies.py, dictionaries.py  (read the CSVs)
    ├── ats/                 ← one file per job-board provider
    ├── labeling/            ← labeler.py  (keyword matching, no I/O)
    ├── storage/             ← sqlite.py  (all SQL lives here)
    ├── pipeline/            ← crawl.py  (the order of the steps)
    └── cli/                 ← main.py  (talentry-crawl command)
```

## Rules (keep it boring)

1. **Dependencies only flow one way.** `models` ← `config`, `ats`, `labeling`, `storage` ← `pipeline` ← `cli`.
   `ats`, `labeling` and `storage` never import each other; only `pipeline` knows the order (so `ats` never imports `storage`, and `storage` never imports `ats`).
   The one small exception: `storage` reads the `output/` folder location from `config/paths.py`.
2. **One full-API ATS = one file** under `ats/`, plus one line in `ats/__init__.py` (`REGISTRY`). Providers that need a browser bootstrap or a separate detail phase belong in a `providers/<name>/` package instead; do not hide a hybrid provider behind a single `ats/` file.
3. **CSV is the source of truth for "what to crawl".** The database only holds *jobs found*.
4. **Only a successful fetch can close jobs.** If a board's site is down, its jobs stay open. A job is closed only when we successfully read the page and it wasn't there.
5. **The crawler has no HTTP API.** It is a background worker. The website reads the same database later; it never calls this code.

## Where things go: "I want to change X"

| I want to… | Open |
|-----------|------|
| crawl one more company | `data/companies.csv` + `data/boards.csv` (no code) |
| label more technologies / titles | `data/technologies.csv`, `occupations.csv`, `seniority.csv` (no code) |
| support a new full-API ATS | new `ats/<name>.py` + one `REGISTRY` line |
| support a hybrid ATS (API + browser/detail) | new `providers/<name>/` package |
| change how jobs are labeled | `labeling/labeler.py` |
| add a column to the database | `storage/sqlite.py` (`SCHEMA` + `SAVE_JOB`) and the `Job` model |
| move from SQLite to Postgres | `storage/` only |

## Example path for one Stripe job

1. `config` reads `stripe,stripe-careers,…,greenhouse,{token:stripe}` from `data/boards.csv`
2. `pipeline` asks `ats.greenhouse` to fetch that board
3. Greenhouse's API returns job JSON; `ats` turns each item into a `Job`
4. `labeling` reads the title "Senior Backend Engineer" → `seniority=senior`, `occupation=backend-developer`, and finds `python`, `aws` in the description
5. `storage` saves the job as `open`, and marks any earlier Stripe job that is no longer listed as `closed`
6. Done. The website (future) reads the database.
