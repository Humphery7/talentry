import Link from 'next/link'
import { Suspense } from 'react'
import type { Metadata } from 'next'
import AuthModal from '@/components/landing/AuthModal'
import { Brand, Li } from '@/components/landing/icons'
export const metadata: Metadata = { title: { absolute: 'Talentry · Real opportunities for your next chapter' } }
const FEATS = [['shield', 'Verified opportunities', 'No scams. Just real jobs and scholarships from trusted sources.'], ['target', 'Personalised for you', 'Opportunities that match your skills, interests and goals.'], ['clock', 'Track and apply', 'Stay organised and never miss a deadline.'], ['cube', 'Build your future', 'Get career and study resources, guides and tips.']] as const
const STEPS = [['01', 'Create your profile', 'Tell us about your skills, interests and goals.'], ['02', 'Get matched', 'We find the best jobs and scholarships for you.'], ['03', 'Apply and grow', 'Take the next step in your journey.']]
export default function Landing() {
  return (
    <>
      <header className="lp-w lp-nav">
        <Link href="/" aria-label="Talentry home"><Brand /></Link>
        <nav aria-label="Primary"><Link href="/jobs">Jobs</Link><a href="#features">Scholarships</a><Link href="/about">About</Link></nav>
        <div className="r"><Link href="/?auth=login" scroll={false}>Log in</Link><Link href="/?auth=signup" scroll={false} className="pill">Get started</Link></div>
      </header>
      <main>
        <section className="lp-w hero">
          <div>
            <span className="tag">Jobs &amp; Scholarships</span>
            <h1>Real opportunities for your next chapter.</h1>
            <p>Talentry helps you find verified jobs and scholarships that match your skills, interests and goals. Build your future with opportunities from trusted employers and institutions.</p>
            <div className="cta"><Link href="/?auth=signup" scroll={false} className="pill">Get started <Li n="arrow" /></Link><a href="#features" className="pill o">Learn more</a></div>
            <dl className="stats2">{[['10k+', 'Active opportunities'], ['500+', 'Trusted employers & schools'], ['50+', 'Countries']].map(([n, l]) => <div key={l}><dt>{n}</dt><dd>{l}</dd></div>)}</dl>
          </div>
          <div className="vis">
            <div className="img" role="img" aria-label="A young man looking toward the city skyline at sunset" />
            <p className="hw">Better<br />opportunities.<br />Bigger dreams.</p>
            <div className="fc a"><span className="ic"><Li n="brief" /></span><div><b>Software Engineer</b><small>Meta • Remote</small><i>Full-time</i></div><Li n="chev" /></div>
            <div className="fc b"><span className="ic"><Li n="cap" /></span><div><b>Computer Science Scholarship</b><small>University of Toronto</small><i>Fully Funded</i></div><Li n="chev" /></div>
          </div>
        </section>
        <section className="lp-w feat" id="features">
          <div><h2>More than just jobs and scholarships.</h2><p>Get personalised recommendations, track your applications, and access resources to help you grow, all in one place.</p></div>
          <div className="fg">{FEATS.map(([i, t, d]) => <div key={t} className="fi"><span className="ic"><Li n={i} /></span><h3>{t}</h3><p>{d}</p></div>)}</div>
        </section>
        <section className="lp-w"><div className="how" id="how">
          <div><span className="tag">How it works</span><h2>Your future, step by step.</h2><p>Getting started is simple. Create your account, set your preferences, and let Talentry do the rest.</p><Link href="/?auth=signup" scroll={false} className="ln">Learn more <Li n="arrow" /></Link></div>
          <ol>{STEPS.map(([n, t, d]) => <li key={n}><span className="ic">{n}</span><h3>{t}</h3><p>{d}</p></li>)}</ol>
        </div></section>
      </main>
      <footer className="ft"><div className="lp-w">
        <Brand inv /><nav aria-label="Footer"><Link href="/jobs">Jobs</Link><a href="#features">Scholarships</a><Link href="/about">About</Link></nav>
        <div className="soc">{(['tw', 'in', 'ig', 'yt'] as const).map(n => <a key={n} href="#" aria-label={n}><Li n={n} /></a>)}</div>
      </div></footer>
      <Suspense><AuthModal /></Suspense>
    </>
  )
}
