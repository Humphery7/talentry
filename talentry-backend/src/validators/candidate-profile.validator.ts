import { optionalString, throwIfInvalid, type Input } from './rules.js';

export interface CandidateProfileInput {
  headline: string | null;
  currentTitle: string | null;
  yearsExperience: number | null;
  location: string | null;
  phone: string | null;
  linkedinUrl: string | null;
  githubUrl: string | null;
  websiteUrl: string | null;
  summary: string | null;
}

export function parseCandidateProfile(
  body: Input = {},
): CandidateProfileInput {
  const errors: string[] = [];

  function text(field: string, max: number): string | null {
    const value = optionalString(body, field, errors);
    if (value === undefined) return null;
    const trimmed = value.trim();
    if (trimmed.length > max) {
      errors.push(`${field} must be shorter than or equal to ${max} characters`);
    }
    return trimmed || null;
  }

  // Links are stored with a scheme so the agent can type them into forms.
  function url(field: string): string | null {
    const value = text(field, 300);
    if (!value) return null;
    return /^https?:\/\//i.test(value) ? value : `https://${value}`;
  }

  let yearsExperience: number | null = null;
  const rawYears = body.yearsExperience;
  if (rawYears !== undefined && rawYears !== null && rawYears !== '') {
    if (
      typeof rawYears !== 'number' ||
      !Number.isInteger(rawYears) ||
      rawYears < 0 ||
      rawYears > 80
    ) {
      errors.push('yearsExperience must be an integer between 0 and 80');
    } else {
      yearsExperience = rawYears;
    }
  }

  throwIfInvalid(errors);
  return {
    headline: text('headline', 160),
    currentTitle: text('currentTitle', 120),
    yearsExperience,
    location: text('location', 120),
    phone: text('phone', 40),
    linkedinUrl: url('linkedinUrl'),
    githubUrl: url('githubUrl'),
    websiteUrl: url('websiteUrl'),
    summary: text('summary', 2000),
  };
}
