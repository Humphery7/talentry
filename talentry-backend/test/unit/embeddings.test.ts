import { describe, expect, it } from 'vitest';
import { buildProfileText } from '../../src/services/candidate-profile.service.js';
import { buildJobText } from '../../src/services/jobs.service.js';

describe('buildProfileText', () => {
  it('includes provided fields and skips null ones', () => {
    const text = buildProfileText({
      headline: ' Frontend Engineer ',
      currentTitle: null,
      yearsExperience: 0,
      location: 'Lagos',
      summary: null,
      cvText: 'Built design systems.',
    });

    expect(text).toBe(
      'Headline: Frontend Engineer\n\n' +
        'Years of experience: 0\n\n' +
        'Location: Lagos\n\n' +
        'CV:\nBuilt design systems.',
    );
  });

  it('returns an empty string when nothing was provided', () => {
    expect(
      buildProfileText({
        headline: null,
        currentTitle: null,
        yearsExperience: null,
        location: null,
        summary: null,
        cvText: null,
      }),
    ).toBe('');
  });
});

describe('buildJobText', () => {
  it('includes job fields and strips HTML from the description', () => {
    const text = buildJobText({
      title: 'Senior Frontend Engineer',
      description: '<p>Build <strong>accessible</strong> web apps.</p>',
      companyName: 'Acme',
      locations: ['Lagos', 'Remote'],
      workplaceType: 'Remote',
      employmentType: 'Full time',
      seniority: 'senior',
      occupation: 'frontend-developer',
      technologies: ['react', 'typescript'],
    });

    expect(text).toBe(
      'Job title: Senior Frontend Engineer\n\n' +
        'Company: Acme\n\n' +
        'Location: Lagos, Remote\n\n' +
        'Workplace: Remote\n\n' +
        'Employment type: Full time\n\n' +
        'Seniority: senior\n\n' +
        'Occupation: frontend developer\n\n' +
        'Technologies: react, typescript\n\n' +
        'Description:\nBuild accessible web apps.',
    );
  });

  it('leaves out fields that are missing', () => {
    expect(buildJobText({ title: 'Designer', description: null })).toBe(
      'Job title: Designer',
    );
    expect(
      buildJobText({ title: null, description: null, locations: [] }),
    ).toBe('');
  });
});
