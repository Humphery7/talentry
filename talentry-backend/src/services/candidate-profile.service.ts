import { pool } from '../db/pool.js';
import type { CandidateProfileInput } from '../validators/candidate-profile.validator.js';
import { createEmbedding } from './embedding.service.js';

const COLUMNS = `
  user_id AS "userId", headline, current_title AS "currentTitle",
  years_experience AS "yearsExperience", location, summary,
  cv_filename AS "cvFilename", cv_updated_at AS "cvUpdatedAt",
  updated_at AS "updatedAt"
`;

const SELECT = `SELECT ${COLUMNS} FROM candidate_profiles`;

interface ProfileTextSource {
  headline: string | null;
  currentTitle: string | null;
  yearsExperience: number | null;
  location: string | null;
  summary: string | null;
  cvText: string | null;
}

// The embedding model only reads the first part of a long document anyway.
const MAX_CV_TEXT = 8_000;

/** Builds the text that represents a candidate. Null fields are left out. */
export function buildProfileText(profile: ProfileTextSource): string {
  const parts: string[] = [];

  function add(label: string, value: string | null | undefined) {
    const text = value?.trim();
    if (text) parts.push(`${label}: ${text}`);
  }

  add('Headline', profile.headline);
  add('Current title', profile.currentTitle);
  if (profile.yearsExperience !== null) {
    parts.push(`Years of experience: ${profile.yearsExperience}`);
  }
  add('Location', profile.location);
  add('Summary', profile.summary);

  const cvText = profile.cvText?.trim();
  if (cvText) {
    parts.push(`CV:\n${cvText.slice(0, MAX_CV_TEXT)}`);
  }

  return parts.join('\n\n');
}

/** Returns null when the user has not filled in a profile yet. */
export async function get(userId: string) {
  const { rows } = await pool.query(`${SELECT} WHERE user_id = $1`, [userId]);
  return rows[0] ?? null;
}

export async function save(userId: string, input: CandidateProfileInput) {
  const { rows } = await pool.query(
    `INSERT INTO candidate_profiles
       (user_id, headline, current_title, years_experience, location, summary)
     VALUES ($1, $2, $3, $4, $5, $6)
     ON CONFLICT (user_id) DO UPDATE SET
       headline = EXCLUDED.headline,
       current_title = EXCLUDED.current_title,
       years_experience = EXCLUDED.years_experience,
       location = EXCLUDED.location,
       summary = EXCLUDED.summary,
       updated_at = now()
     RETURNING ${COLUMNS}`,
    [
      userId,
      input.headline,
      input.currentTitle,
      input.yearsExperience,
      input.location,
      input.summary,
    ],
  );
  await updateEmbedding(userId);
  return rows[0];
}

/**
 * Rebuilds the vector from the current profile fields and CV text. A failure
 * is logged but does not undo the profile save.
 */
async function updateEmbedding(userId: string) {
  try {
    await refreshProfileEmbedding(userId);
  } catch (err) {
    console.error('Could not update profile embedding:', err);
  }
}

export async function refreshProfileEmbedding(userId: string) {
  const { rows } = await pool.query(
    `SELECT headline, current_title AS "currentTitle",
            years_experience AS "yearsExperience", location, summary,
            cv_data AS "cvText"
     FROM candidate_profiles WHERE user_id = $1`,
    [userId],
  );
  const profile = rows[0] as ProfileTextSource | undefined;
  if (!profile) return;

  const text = buildProfileText(profile);
  if (!text) {
    await pool.query(
      `UPDATE candidate_profiles
       SET profile_embedding = NULL, embedding_updated_at = now()
       WHERE user_id = $1`,
      [userId],
    );
    return;
  }

  const embedding = await createEmbedding(text);
  await pool.query(
    `UPDATE candidate_profiles
     SET profile_embedding = $2::vector, embedding_updated_at = now()
     WHERE user_id = $1`,
    [userId, JSON.stringify(embedding)],
  );
}

/** Replaces the user's CV. One CV per account for now. */
export async function saveCv(
  userId: string,
  filename: string,
  mime: string,
  data: string,
) {
  const { rows } = await pool.query(
    `INSERT INTO candidate_profiles (user_id, cv_filename, cv_mime, cv_data, cv_updated_at)
     VALUES ($1, $2, $3, $4, now())
     ON CONFLICT (user_id) DO UPDATE SET
       cv_filename = EXCLUDED.cv_filename,
       cv_mime = EXCLUDED.cv_mime,
       cv_data = EXCLUDED.cv_data,
       cv_updated_at = now(),
       updated_at = now()
     RETURNING ${COLUMNS}`,
    [userId, filename, mime, data],
  );
  await updateEmbedding(userId);
  return rows[0];
}

export async function getCv(userId: string) {
  const { rows } = await pool.query(
    `SELECT cv_filename AS filename, cv_data AS data
     FROM candidate_profiles WHERE user_id = $1`,
    [userId],
  );
  const row = rows[0];
  if (!row?.data) return null;
  return row as { filename: string; data: string };
}

export async function parsePDF(data: Buffer): Promise<string> {
  // Loaded only for uploads, not with the rest of the profile API.
  const { PDFParse } = await import('pdf-parse');
  const parser = new PDFParse({ data: data });
  const result = await parser.getText();
  return result.text;
}
