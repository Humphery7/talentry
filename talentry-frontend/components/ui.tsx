import type { Job } from '@/lib/data'
const D = { mail: 'M3 7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zM3 8l9 6 9-6', user: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21c0-4 4-6 8-6s8 2 8 6', bm: 'M6 3h12v18l-6-4-6 4z', clock: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 2', set: 'M4 7h10M18 7h2M4 17h2M10 17h10M14 4v6M6 14v6', find: 'M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM20 20l-4-4', chk: 'M3 6h12M3 12h8M3 18h6M14 17l3 3 5-6' }
export const Icon = ({ n }: { n: keyof typeof D }) => <svg viewBox="0 0 24 24" aria-hidden="true"><path d={D[n]} /></svg>
export const Verified = () => <svg viewBox="0 0 24 24" aria-label="Verified"><circle cx="12" cy="12" r="10" /><path d="m7.5 12.5 3 3 6-6" /></svg>
export const CompanyLogo = ({ job }: { job: Pick<Job, 'bg' | 'ch'> }) => (
  <span className="logo-c" aria-hidden="true" style={{ background: job.bg, color: job.bg === '#fff' ? '#4285f4' : '#fff', border: job.bg === '#fff' ? '1px solid #eee' : 0, fontSize: job.ch.length > 3 ? 11 : 22 }}>{job.ch}</span>
)
export const PageHead = ({ title, sub }: { title: string; sub: string }) => <div className="ph"><h1>{title}</h1><p>{sub}</p></div>
