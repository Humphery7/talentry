# Continue Talentry Crawler ATS Coverage

Copy this file's contents as the prompt when resuming.

## Repo and working setup

Repo: `/Users/humpheryotuoniyo/talentry`
Crawler: `/Users/humpheryotuoniyo/talentry/crawler`
Package: `/Users/humpheryotuoniyo/talentry/crawler/src/talentry_crawler`
Tests: `/Users/humpheryotuoniyo/talentry/crawler/tests/test_ats.py`
Boards: `/Users/humpheryotuoniyo/talentry/crawler/data/boards.csv`

Environment: macOS, zsh. Use `grep`; `rg` is unavailable.

Run tests with:

```bash
cd /Users/humpheryotuoniyo/talentry/crawler
PYTHONPATH=src pytest -q
```

Do not use plain `pytest`; an installed/stale package can shadow the source tree.
Never edit `crawler/build/lib/`. Do not touch unrelated dirty worktree files in
`talentry-backend`, `talentry-career`, or `talentry-frontend`. Do not commit
unless explicitly asked.

## Goal

Reach coverage parity with jobseek's 106 ATS/monitor types, using their monitor
and scraper implementations as the reference architecture, adapted to our
crawler.

We currently only have the API-only `ats/` layer. Scraper-only and API+scraper
support still need to be built. Do not claim parity until all three layers are
implemented and tested.

Read these first:

- `crawler/ARCHITECTURE.md`
- `crawler/README.md`
- `crawler/src/talentry_crawler/ats/__init__.py`
- `crawler/src/talentry_crawler/pipeline/crawl.py`
- `crawler/src/talentry_crawler/models/models.py`
- `crawler/tests/test_ats.py`
- `crawler/data/boards.csv`

Upstream references:

- `/var/folders/5j/tnv7r_5x4hs0vcyc9rw9plcw0000gq/T/opencode/jobseek-monitors`
- `/var/folders/5j/tnv7r_5x4hs0vcyc9rw9plcw0000gq/T/opencode/jobseek-docs`
- `/var/folders/5j/tnv7r_5x4hs0vcyc9rw9plcw0000gq/T/opencode/jobseek-paths.txt`

Important: only jobseek monitors and docs were extracted locally. Their scraper
implementations were not available; the `jobseek.tar.gz` archive is truncated.
If scraper details are needed, inspect the docs/monitor code first, and ask for
the missing scraper source rather than guessing.

## Current verified state

- Registry: 41 API-only adapters in `ats/__init__.py`.
- Tests: 76 passing.
- README adapter list is updated for the latest batch.
- Latest batch added, registered, tested, and live-smoked:
  `brassring`, `bytedance`, `dvinci`, `earcu`, `fenbi`.
- Registry types that appear in `boards.csv`: 39.
- Registry includes two types with zero board rows: `dvinci`, `hireology`.
- `boards.csv`: 7,885 board rows and 102 distinct monitor types.
- Upstream jobseek registry: 106 monitor types.
- Four upstream types are absent from `boards.csv`: `bite`, `dvinci`, `herp`,
  `hireology`. `dvinci` and `hireology` are already implemented; `bite` and
  `herp` are not.
- Current pipeline calls `get_discoverer(board.monitor_type)` only.
  `scraper_type` and `scraper_config` exist in CSV/Board but are not used yet.
- There is no `providers/` or `scrapers/` package yet. Adding one requires a
  pipeline integration change. Stop and explain the architectural impact before
  implementing that layer.

## Coverage counts

Universe: 106 distinct ATS/monitor types. Do not confuse this with the 7,885
board rows.

| Category | Total | Done | Left |
|---|---:|---:|---:|
| API-only | 50 | 41 | 9 |
| Scraper-only | 0 | 0 | 14 |
| API+scraper | 0 | 0 | 42 |

Total left: 65.

The earlier scraper-only count of 7 was wrong. The correct figure is 14. The 7
only covered generic monitor strategies (`dom`, `sitemap`, `inline`,
`api_sniffer`, `nextdata`, `join`, `linkedin`). Reconstruct and verify the
50/14/42 split before starting; report any discrepancy instead of silently
changing the tracker.

The 7,885 board rows break down approximately as:

- API-only: 4,529
- Scraper-only: 1,964
- API+scraper: 1,392

Treat the type-level 50/14/42 split as authoritative for coverage tracking.

## Remaining API-only candidates

Board-row counts:

- `rss` — 407
- `dayforce` — 10
- `unifr` — 9
- `darwinbox` — 5
- `jobbank104` — 4
- `cvwarehouse` — 2
- `kipt` — 1
- `prospective` — 1
- `unisante` — 1

Known probe results:

- `jobbank104`: public API returns Cloudflare 403 across token variants.
- `prospective`: public API returned 400/404.
- `darwinbox`: Cloudflare challenge.
- `dayforce`: needs browser bootstrap / NextAuth CSRF session; likely belongs in
  API+scraper rather than API-only.
- `rss`: XML feeds are feasible but cover 407 boards; high-value batch.
- `unisante`, `unifr`, `cvwarehouse`, `kipt`: previously judged “not pure”;
  re-audit before implementing.
- Reclassify any candidate that needs a browser or separate detail phase.

## Latest adapter details to preserve

`brassring`:

- Direct HTTP, no browser.
- GET board page with `partnerid`/`siteid`, extract
  `__RequestVerificationToken` and `#CookieValue`.
- POST `/TgNewUI/Search/Ajax/MatchedJobs`.
- Paginate via `/TgNewUI/Search/Ajax/ProcessSortAndShowMoreJobs` with
  `SortType` and `pageNumber`.
- Detail pages expose `preLoadJSON`; use it to fill missing locations.
- Live counts: adm-na 49, adm-global 297; known counts include adm-us 507 and
  Caterpillar 132.

`bytedance`:

- Global: `https://joinbytedance.com/search` via
  `POST /api/v1/public/supplier/search/job/posts`, header
  `x-tt-env: boe_epam_api`, limit 1000.
- CN experienced/campus: `POST /api/v1/search/job/posts` with `portal_type`
  2/3 and headers `website-path`, `portal-platform`, `portal-channel`,
  `origin`, `referer`, browser user-agent.
- Experienced filters: `GET /api/v1/config/job/filters/2`, using
  `data.job_type_list` and `data.job_type_count_map`; partition categories if a
  count approaches the 10,000-result cap.
- Live counts: 1,435 global; 10,676 experienced; 7,032 campus.

`dvinci`:

- `GET https://{slug}.dvinci-hr.com/jobPublication/list.json`.
- Live: inverto 71, rpc 11.
- No `boards.csv` rows, but live boards exist.

`earcu`:

- XML feed adapter. dnata feed works (11 jobs live).
- Aldi feeds are Cloudflare 403.
- Only 1 of 3 sample boards is live.

`fenbi`:

- Inventory is embedded in a JS chunk imported by the main bundle.
- Fetch main `main-*.js`, then imported `chunk-*.js` files, and search for
  `this.joinUsArr=`.
- Do not regress to main-bundle-only parsing.
- Live: fulltime 31, parttime 9.

## Architecture rules

- API-only full-content provider: `ats/<name>.py` + one `REGISTRY` line.
- Browser-bootstrap or separate detail-phase provider: `providers/<name>/`
  package, per `ARCHITECTURE.md`; do not hide hybrids in `ats/`.
- Scraper-only providers need a scraper layer and pipeline wiring. Design this
  before implementing it.
- Adapter contract:
  `async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]`.
- Use `httpx`, `asyncio`, and the existing `Board`/`Job` models.
- `Board` carries `monitor_type`, `monitor_config`, `scraper_type`,
  `scraper_config`.
- Preserve existing validation and error-handling conventions.
- Tests must be offline and use `httpx.MockTransport`.

## Workflow for each adapter/batch

1. Read the upstream jobseek monitor implementation.
2. Find sample board URLs in `boards.csv` and inspect their config.
3. Probe the live endpoint with a small script before writing code.
4. Implement the adapter.
5. Register it.
6. Add tests with `httpx.MockTransport`.
7. Run `PYTHONPATH=src pytest -q`.
8. Live-smoke at least one real board.
9. Update `crawler/README.md`.
10. Report: adapters added, registry total, tests passing, live counts, blockers.

Work in small batches, usually 3-5 providers. Do not attempt all 65 remaining
types in one session. After each batch, give updated counts for API-only,
scraper-only, and API+scraper.

## Recommended order

1. Confirm current registry/test state and reconstruct the 50/14/42 split.
2. Re-audit the 9 remaining API-only candidates; reclassify `dayforce` if needed.
3. Implement the easiest remaining API-only adapters with tests.
4. Build the scraper-only layer (14 types).
5. Build the API+scraper layer (42 types), starting with high-board-count
   providers.
6. Keep the coverage table updated after every batch.

If a provider requires a browser, scraper layer, or pipeline change, stop and
explain the architectural impact before implementing it.

Start by checking `git status`, confirming the 41 registry entries and 76 tests,
then propose the next small batch with its classification and blockers.
