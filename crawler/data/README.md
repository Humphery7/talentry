# Input data

CSVs that define **what** to crawl and **what to label with**. The crawler reads these; it does not invent companies.

| File | Purpose | Used by |
|------|---------|---------|
| `companies.csv` | Who we track (slug, name, website, logos, industry…) | `config/companies.py` → `companies` table |
| `boards.csv` | Where each company's jobs live + which ATS adapter reads them | `config/boards.py` → the crawl |
| `seniority.csv` | Seniority levels and the words that mean them | `labeling/` |
| `occupations.csv` | Job types, with names in many languages + aliases | `labeling/` |
| `technologies.csv` | Technologies and the text patterns that mean them (`cs` flag = exact case) | `labeling/` |
| `industries.csv` | Industry id → name (companies.csv uses the id) | `config/companies.py` |

`boards.csv` points at `companies.csv`: every board's `company_slug` must match a company `slug`.
A company can have several boards; each board belongs to one company.

To teach the labeler a new word, add it to the `aliases` column (words separated by `|`). No code change is needed.

See [`../ARCHITECTURE.md`](../ARCHITECTURE.md) for how these feed the crawl.
