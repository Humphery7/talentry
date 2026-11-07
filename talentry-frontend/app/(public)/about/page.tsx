import type { Metadata } from 'next'
import Link from 'next/link'
import { PageHead } from '@/components/ui'
import { getLiveCounts } from '@/lib/api'

export const metadata: Metadata = {
  title: 'About',
  description:
    'What Talentry is, where its jobs come from, and what you can do here.',
}

const STEPS = [
  [
    '1',
    'We read the source',
    'A background crawler checks company career pages on Greenhouse, Ashby and Lever, so listings come from the employer rather than another job board.',
  ],
  [
    '2',
    'Each role is cleaned and labelled',
    'Listings are normalised and tagged by seniority, occupation and the technologies they mention, which is what powers the filters.',
  ],
  [
    '3',
    'Stale roles are closed',
    'When a role disappears from the company page it is marked closed instead of deleted, so the site stops showing you dead listings.',
  ],
] as const

const FEATURES = [
  [
    '/jobs',
    'Search open roles',
    'Filter by keyword, location, experience level, job type, industry and salary.',
  ],
  [
    '/companies',
    'Browse companies',
    'See who is hiring and jump straight to their open roles.',
  ],
  [
    '/saved',
    'Save a shortlist',
    'Bookmark roles and come back to them later; saved jobs stay in your browser.',
  ],
] as const

const PREVIEWS = [
  [
    '/interview',
    'Mock interview',
    'Practise common questions and check how long your answers are.',
  ],
  [
    '/coach',
    'Career coach',
    'Read short playbooks on negotiation, switching careers and portfolios.',
  ],
] as const

export default async function About() {
  const counts = await getLiveCounts()

  return (
    <div>
      <PageHead
        title="About Talentry"
        sub="A searchable list of jobs, gathered from the companies doing the hiring."
      />

      <section className="panel about-lead">
        <h2>What Talentry is</h2>
        <p>
          Talentry is a job board built on company career pages. Instead of
          copying listings from other job boards, we read employers&apos; own
          postings and keep them in one searchable place, so what you see is
          closer to what the company is actually hiring for.
        </p>
        <p>
          Search and filter the roles, check the details, save the ones you
          like, and apply from the job page. It is a smaller, more direct way
          to job hunt.
        </p>
      </section>

      <section className="about-section">
        <h2>Talentry right now</h2>
        {counts ? (
          <div className="cgrid">
            <div className="cc">
              <span className="big">
                {counts.openJobs.toLocaleString('en-US')}
              </span>
              <span className="m">open roles indexed</span>
            </div>
            <div className="cc">
              <span className="big">
                {counts.companies.toLocaleString('en-US')}
              </span>
              <span className="m">companies watched</span>
            </div>
            <div className="cc">
              <span className="big">3</span>
              <span className="m">
                job-board sources: Greenhouse, Ashby and Lever
              </span>
            </div>
          </div>
        ) : (
          <p>
            Live counts are unavailable because the API cannot be reached right
            now. Start the backend to see the current numbers.
          </p>
        )}
      </section>

      <section className="about-section">
        <h2>Where the jobs come from</h2>
        <p>
          Every role traces back to a public company career page. Nothing is
          invented or reposted from an aggregator.
        </p>
        <div className="cgrid">
          {STEPS.map(([n, title, body]) => (
            <div key={n} className="cc">
              <span className="big">{n}</span>
              <b>{title}</b>
              <span className="m">{body}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="about-section">
        <h2>What you can do here</h2>
        <div className="cgrid">
          {FEATURES.map(([href, title, body]) => (
            <Link key={href} href={href} className="cc">
              <b>{title}</b>
              <span className="m">{body}</span>
            </Link>
          ))}
        </div>
      </section>

      <section className="about-section">
        <h2>Still in preview</h2>
        <p>
          These screens are mock-ups with sample content for now. They are not
          connected to a live analyser or coach yet.
        </p>
        <div className="cgrid">
          {PREVIEWS.map(([href, title, body]) => (
            <Link key={href} href={href} className="cc">
              <b>
                {title}
                <span className="prev">Preview</span>
              </b>
              <span className="m">{body}</span>
            </Link>
          ))}
        </div>
      </section>

      <div className="about-cta">
        <Link className="btn" href="/jobs">
          Browse open roles
        </Link>
        <Link className="btn" href="/?auth=signup">
          Create an account
        </Link>
      </div>
    </div>
  )
}
