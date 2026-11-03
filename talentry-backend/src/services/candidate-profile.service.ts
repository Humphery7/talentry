import { pool } from '../db/pool.js';
import type { CandidateProfileInput } from '../validators/candidate-profile.validator.js';
import { postCareer } from './career.service.js';

const COLUMNS = `
  user_id AS "userId", headline, current_title AS "currentTitle",
  years_experience AS "yearsExperience", location, summary,
  cv_filename AS "cvFilename", cv_updated_at AS "cvUpdatedAt",
  updated_at AS "updatedAt"
`;

const SELECT = `SELECT ${COLUMNS} FROM candidate_profiles`;

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

/** Lets the career service rebuild the profile vector from the saved row. */
async function updateEmbedding(userId: string) {
  try {
    await postCareer<{ embedded: boolean }>(
      `/profiles/${userId}/embedding`,
      {},
    );
  } catch (err) {
    console.error('Could not update profile embedding:', err);
  }
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
