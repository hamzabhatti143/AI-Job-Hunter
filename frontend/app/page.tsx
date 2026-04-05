import type { Metadata } from 'next'
import Link from 'next/link'
import PublicHeader from '@/components/PublicHeader'
import PublicFooter from '@/components/PublicFooter'

export const metadata: Metadata = {
  title: 'ApplyAI — AI Job Matching & Automated Applications',
  description: 'Upload your resume and let ApplyAI match you with relevant jobs, write personalized cold emails, and send applications — with your approval every step of the way.',
}

const features = [
  {
    icon: '🎯',
    title: 'Smart Role Matching',
    desc: 'AI scores every job against your skills, experience, and role preference. Only relevant positions surface — no noise.',
  },
  {
    icon: '✉️',
    title: 'Personalized Cold Emails',
    desc: 'GPT-4o-mini writes a tailored outreach email for each matched role, referencing your specific skills and the exact job title.',
  },
  {
    icon: '✅',
    title: 'You Always Approve',
    desc: 'Every email lands in your inbox for review first. Click Approve to send, or Reject to discard — no surprises.',
  },
  {
    icon: '📎',
    title: 'Resume Auto-Attached',
    desc: 'Your resume is automatically attached to every approved email. No manual uploads each time.',
  },
  {
    icon: '🔍',
    title: 'Multi-Source Job Search',
    desc: 'Scans RemoteOK, Remotive, and Arbeitnow simultaneously to find the most relevant live opportunities.',
  },
  {
    icon: '📊',
    title: 'Full Tracking Dashboard',
    desc: 'See matched jobs, pending approvals, sent applications, and activity logs in one clean interface.',
  },
]

const steps = [
  { n: '01', title: 'Create your account', desc: 'Sign up with your name, email, OpenAI API key, and Gmail credentials for sending emails.' },
  { n: '02', title: 'Upload your resume', desc: 'Upload a PDF or DOCX resume. The AI extracts your skills and experience automatically.' },
  { n: '03', title: 'Set your preferences', desc: 'Enter your target role (e.g. "Frontend Developer") and location (e.g. "Remote").' },
  { n: '04', title: 'AI finds & ranks jobs', desc: 'The agent scrapes live listings and scores each job for relevance — only 40%+ matches shown.' },
  { n: '05', title: 'Emails are drafted', desc: 'Personalized application emails are written for your top matches and sent to your inbox for review.' },
  { n: '06', title: 'You approve & send', desc: 'Review each draft, click Approve, and the email goes to the recruiter with your resume attached.' },
]

const stats = [
  { value: '3 APIs', label: 'Job boards searched simultaneously' },
  { value: '< $0.01', label: 'Cost per full pipeline run' },
  { value: '~60s', label: 'From upload to draft emails ready' },
  { value: '100%', label: 'You control every send' },
]

export default function Home() {
  return (
    <>
      <PublicHeader />

      <main>
        {/* ── Hero ──────────────────────────────────────────────────────── */}
        <section className="relative overflow-hidden bg-gray-950 pt-24 pb-32">
          {/* glow */}
          <div className="absolute inset-0 pointer-events-none">
            <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[500px] bg-blue-600/10 rounded-full blur-3xl" />
          </div>
          <div className="relative max-w-5xl mx-auto px-6 text-center">
            <div className="inline-flex items-center gap-2 bg-blue-900/40 border border-blue-700/50 text-blue-300 text-sm px-4 py-1.5 rounded-full mb-8">
              <span className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-pulse" />
              AI-powered job matching — now live
            </div>
            <h1 className="text-5xl md:text-6xl font-bold text-white leading-tight tracking-tight">
              Land more interviews<br />
              <span className="text-blue-400">on autopilot</span>
            </h1>
            <p className="mt-6 text-xl text-gray-400 max-w-2xl mx-auto leading-relaxed">
              Upload your resume. ApplyAI matches you with relevant jobs, writes personalized
              cold emails, and sends applications — with your approval every step of the way.
            </p>
            <div className="mt-10 flex flex-col sm:flex-row gap-4 justify-center">
              <Link href="/signup"
                className="bg-blue-600 hover:bg-blue-500 text-white font-semibold px-8 py-3.5 rounded-xl transition text-lg shadow-lg shadow-blue-600/20">
                Start for free
              </Link>
              <Link href="/guide"
                className="border border-gray-700 hover:border-gray-500 text-gray-300 hover:text-white font-semibold px-8 py-3.5 rounded-xl transition text-lg">
                See how it works
              </Link>
            </div>
            <p className="mt-5 text-gray-600 text-sm">No credit card required · Uses your own OpenAI key · ~$0.01 per run</p>
          </div>
        </section>

        {/* ── Stats bar ────────────────────────────────────────────────── */}
        <section className="border-y border-gray-800 bg-gray-900/50">
          <div className="max-w-5xl mx-auto px-6 py-10 grid grid-cols-2 md:grid-cols-4 gap-8">
            {stats.map(s => (
              <div key={s.label} className="text-center">
                <div className="text-3xl font-bold text-white">{s.value}</div>
                <div className="text-gray-500 text-sm mt-1">{s.label}</div>
              </div>
            ))}
          </div>
        </section>

        {/* ── How it works ─────────────────────────────────────────────── */}
        <section id="how-it-works" className="py-24 max-w-5xl mx-auto px-6">
          <div className="text-center mb-16">
            <h2 className="text-4xl font-bold text-white">From resume to application in 6 steps</h2>
            <p className="text-gray-400 mt-3 text-lg">The entire process takes about 60 seconds — then the AI does the work.</p>
          </div>
          <div className="grid md:grid-cols-2 gap-5">
            {steps.map(s => (
              <div key={s.n} className="bg-gray-900 border border-gray-800 rounded-2xl p-6 flex gap-5 items-start">
                <span className="text-4xl font-black text-gray-700 leading-none flex-shrink-0">{s.n}</span>
                <div>
                  <h3 className="text-white font-semibold text-lg">{s.title}</h3>
                  <p className="text-gray-400 text-sm mt-1 leading-relaxed">{s.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* ── Features ────────────────────────────────────────────────── */}
        <section id="features" className="py-24 bg-gray-900/40 border-y border-gray-800">
          <div className="max-w-5xl mx-auto px-6">
            <div className="text-center mb-16">
              <h2 className="text-4xl font-bold text-white">Everything you need to apply smarter</h2>
              <p className="text-gray-400 mt-3 text-lg">One pipeline. Automated. Always under your control.</p>
            </div>
            <div className="grid md:grid-cols-3 gap-5">
              {features.map(f => (
                <div key={f.title} className="bg-gray-900 border border-gray-800 rounded-2xl p-6 space-y-3 hover:border-blue-800 transition">
                  <div className="text-3xl">{f.icon}</div>
                  <h3 className="text-white font-semibold text-lg">{f.title}</h3>
                  <p className="text-gray-400 text-sm leading-relaxed">{f.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── Productivity benefits ────────────────────────────────────── */}
        <section id="benefits" className="py-24 max-w-5xl mx-auto px-6">
          <div className="grid md:grid-cols-2 gap-12 items-center">
            <div className="space-y-6">
              <h2 className="text-4xl font-bold text-white">Stop spending hours on job boards</h2>
              <p className="text-gray-400 text-lg leading-relaxed">
                The average job seeker spends 11 hours a week manually searching boards,
                tailoring resumes, and writing cover letters. ApplyAI compresses all of
                that into a single 60-second pipeline run.
              </p>
              <ul className="space-y-3">
                {[
                  'Searches 3 job boards at once so you miss nothing',
                  'Filters by role relevance — no irrelevant listings',
                  'Writes better cold emails than most humans do',
                  'Tracks every application in one dashboard',
                  'You stay in control — nothing sends without approval',
                ].map(b => (
                  <li key={b} className="flex items-start gap-3 text-gray-300">
                    <span className="text-blue-400 mt-0.5 flex-shrink-0">→</span>
                    {b}
                  </li>
                ))}
              </ul>
            </div>
            <div className="bg-gray-900 border border-gray-800 rounded-2xl p-8 space-y-5">
              <h3 className="text-white font-semibold text-xl">Before vs. After</h3>
              {[
                { before: '3–5 hrs searching boards', after: '1 pipeline run (~60s)', label: 'Job search' },
                { before: '30 min writing each email', after: 'Auto-generated by AI', label: 'Cold outreach' },
                { before: 'Scattered spreadsheet', after: 'Unified dashboard', label: 'Tracking' },
                { before: '~$0 but hours of effort', after: '~$0.01 per run', label: 'Cost' },
              ].map(row => (
                <div key={row.label} className="grid grid-cols-3 gap-4 text-sm border-b border-gray-800 pb-4 last:border-0 last:pb-0">
                  <div className="text-gray-500">{row.label}</div>
                  <div className="text-red-400 line-through">{row.before}</div>
                  <div className="text-green-400">{row.after}</div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── CTA ──────────────────────────────────────────────────────── */}
        <section className="py-24 bg-gray-900/40 border-t border-gray-800">
          <div className="max-w-3xl mx-auto px-6 text-center space-y-6">
            <h2 className="text-4xl font-bold text-white">Ready to automate your job search?</h2>
            <p className="text-gray-400 text-lg">
              Create a free account, upload your resume, and get your first matched jobs in under a minute.
            </p>
            <div className="flex flex-col sm:flex-row gap-4 justify-center pt-2">
              <Link href="/signup"
                className="bg-blue-600 hover:bg-blue-500 text-white font-semibold px-10 py-4 rounded-xl transition text-lg shadow-lg shadow-blue-600/20">
                Get started free
              </Link>
              <Link href="/guide"
                className="border border-gray-700 hover:border-gray-500 text-gray-300 hover:text-white font-semibold px-10 py-4 rounded-xl transition text-lg">
                Read the guide
              </Link>
            </div>
          </div>
        </section>
      </main>

      <PublicFooter />
    </>
  )
}
