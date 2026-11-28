/**
 * Location regions shared by the job search and the career coach.
 *
 * The region definitions live in `shared/job-locations.json` at the repo root
 * because two services need them: this TypeScript API and the Python career
 * service. Keeping one file means "Europe" can never mean one thing on the jobs
 * page and something else in recommendations.
 *
 * Patterns are PostgreSQL regular expressions evaluated with `~*`
 * (case-insensitive). `\m` and `\M` are Postgres word boundaries, which is what
 * keeps `\mus\M` from matching "USA" or "Austin", and `ca\M` from matching
 * "Canada".
 *
 * A location string is split on separators, and each segment is assigned to the
 * region with the longest matching pattern. That resolves accidental overlaps:
 * "Vienna, Virginia, United States" is the US, not Europe, because "Virginia"
 * and "United States" are longer matches than "Vienna"; "Berlin, DE" is Europe,
 * not Delaware. A job listing several cities still belongs to several regions,
 * because each segment is classified independently. Counts are therefore per
 * region, not a partition of all jobs.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

export interface LocationRegion {
  slug: string;
  label: string;
  patterns: string[];
}

interface LocationFile {
  regions: LocationRegion[];
  workplacePatterns: Record<string, string[]>;
}

// `../../../` works from both `src/services/` in development and
// `dist/services/` in production: both land on the repo root.
const FILE = fileURLToPath(
  new URL('../../../shared/job-locations.json', import.meta.url),
);

function load(): LocationFile {
  try {
    return JSON.parse(readFileSync(FILE, 'utf8')) as LocationFile;
  } catch (err) {
    throw new Error(
      `Could not read shared location regions at ${FILE}: ${
        err instanceof Error ? err.message : String(err)
      }`,
    );
  }
}

const shared = load();

export const LOCATION_REGIONS: LocationRegion[] = shared.regions;

/** Each region's patterns as one alternation, which is far cheaper to run. */
export const REGION_REGEXES: Array<{
  slug: string;
  label: string;
  pattern: string;
}> = LOCATION_REGIONS.map((r) => ({
  slug: r.slug,
  label: r.label,
  pattern: `(${r.patterns.join('|')})`,
}));

export const REGION_BY_SLUG: Record<
  string,
  { slug: string; label: string; pattern: string }
> = Object.fromEntries(REGION_REGEXES.map((r) => [r.slug, r]));

/**
 * Workplace filter fallbacks for jobs that never set `workplace_type` but say
 * it in the location text ("Remote", "Distributed", "San Mateo Hybrid").
 */
export const WORKPLACE_LOCATION_PATTERNS: Record<string, string[]> =
  shared.workplacePatterns;

/** Every pattern, used to count jobs that no region claims. */
export const ALL_LOCATION_PATTERNS: string[] = LOCATION_REGIONS.flatMap(
  (r) => r.patterns,
);

/** The same list as one alternation, for "does any region match" checks. */
export const ALL_LOCATION_REGEX = `(${ALL_LOCATION_PATTERNS.join('|')})`;
