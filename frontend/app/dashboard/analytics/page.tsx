'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import api from '@/lib/api'

interface Analytics {
  jobs: {
    total_matched: number
    total_applied: number
    top_matches: number
    avg_match_score: number
    by_source: Record<string, number>
  }
  emails: {
    total_sent: number
    sent_today: number
    sent_this_week: number
    followups_sent: number
    drafts_pending: number
  }
  applications_by_day: { date: string; count: number }[]
}

const SOURCE_LABELS: Record<string, string> = {
  remoteok: 'RemoteOK', remotive: 'Remotive', weworkremotely: 'We Work Remotely',
  arbeitnow: 'Arbeitnow', findwork: 'Findwork', jobicy: 'Jobicy',
  themuse: 'The Muse', serpapi_google_jobs: 'Google Jobs', adzuna: 'Adzuna',
  smartrecruiters: 'Brightspyre', bayt: 'Bayt.com', rozee: 'Rozee.pk',
  acca_global: 'ACCA Global', trabajo_pk: 'Trabajo.org (PK)', bebee: 'Bebee',
  joinimagine: 'Join Imagine', interviewpal: 'InterviewPal',
}

function StatCard({ label, value, sub, color = 'text-blue-400' }: {
  label: string; value: string | number; sub?: string; color?: string
}) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
      <p className="text-gray-500 text-sm">{label}</p>
      <p className={`text-3xl font-bold mt-1 ${color}`}>{value}</p>
      {sub && <p className="text-gray-600 text-xs mt-1">{sub}</p>}
    </div>
  )
}

export default function AnalyticsPage() {
  const router = useRouter()
  const [data, setData] = useState<Analytics | null>(null)
  const [loading, setLoading] = useState(true)
  const [followingUp, setFollowingUp] = useState(false)
  const [followupMsg, setFollowupMsg] = useState('')

  useEffect(() => { fetchAnalytics() }, [])

  const fetchAnalytics = async () => {
    try {
      const res = await api.get('/dashboard/analytics')
      setData(res.data)
    } catch { router.push('/login') }
    finally { setLoading(false) }
  }

  const triggerFollowup = async () => {
    setFollowingUp(true)
    setFollowupMsg('')
    try {
      const res = await api.post('/dashboard/followup')
      const d = res.data
      setFollowupMsg(
        d.followups_drafted > 0
          ? `Created ${d.followups_drafted} follow-up draft(s). Check Application Drafts.`
          : 'No follow-ups needed yet — all applications are recent.'
      )
      fetchAnalytics()
    } catch { setFollowupMsg('Failed to check follow-ups. Please try again.') }
    finally { setFollowingUp(false) }
  }

  if (loading) return <div className="text-gray-400 py-12 text-center">Loading analytics…</div>
  if (!data) return null

  const { jobs, emails, applications_by_day } = data
  const maxCount = Math.max(...applications_by_day.map(d => d.count), 1)

  const sourcesEntries = Object.entries(jobs.by_source).sort((a, b) => b[1] - a[1])

  return (
    <div className="space-y-8 max-w-4xl">
      <div>
        <h2 className="text-2xl font-bold text-white">Analytics</h2>
        <p className="text-gray-500 text-sm mt-1">Track your job search performance and email activity.</p>
      </div>

      {/* Job stats */}
      <section>
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">Job Matches</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label="Total Matched" value={jobs.total_matched} color="text-blue-400" />
          <StatCard label="Applied" value={jobs.total_applied} color="text-green-400" />
          <StatCard label="Top Matches" value={jobs.top_matches} sub="≥70% score" color="text-yellow-400" />
          <StatCard label="Avg Score" value={`${jobs.avg_match_score}%`} color="text-purple-400" />
        </div>
      </section>

      {/* Email stats */}
      <section>
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">Email Activity</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label="Total Sent" value={emails.total_sent} color="text-blue-400" />
          <StatCard label="Sent Today" value={emails.sent_today} color="text-green-400" />
          <StatCard label="This Week" value={emails.sent_this_week} color="text-emerald-400" />
          <StatCard label="Drafts Pending" value={emails.drafts_pending} color="text-yellow-400" />
        </div>
      </section>

      {/* Applications by day chart */}
      <section className="bg-gray-900 border border-gray-800 rounded-xl p-6">
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">Applications — Last 14 Days</h3>
        <div className="flex items-end gap-1 h-24">
          {applications_by_day.map(d => (
            <div key={d.date} className="flex-1 flex flex-col items-center gap-1 group">
              <div
                className="w-full bg-blue-600 rounded-t-sm transition-all group-hover:bg-blue-400"
                style={{ height: `${Math.round((d.count / maxCount) * 80) + (d.count > 0 ? 4 : 0)}px`, minHeight: d.count > 0 ? '4px' : '2px' }}
              />
              <span className="text-gray-700 text-xs hidden md:block">{d.date.slice(5)}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Source distribution */}
      {sourcesEntries.length > 0 && (
        <section className="bg-gray-900 border border-gray-800 rounded-xl p-6">
          <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">Jobs by Source</h3>
          <div className="space-y-3">
            {sourcesEntries.map(([src, count]) => {
              const total = jobs.total_matched || 1
              const pct   = Math.round((count / total) * 100)
              return (
                <div key={src} className="flex items-center gap-3">
                  <span className="text-gray-400 text-sm w-36 truncate">{SOURCE_LABELS[src] || src}</span>
                  <div className="flex-1 bg-gray-800 rounded-full h-2">
                    <div className="bg-blue-500 h-2 rounded-full" style={{ width: `${pct}%` }} />
                  </div>
                  <span className="text-gray-500 text-xs w-8 text-right">{count}</span>
                </div>
              )
            })}
          </div>
        </section>
      )}

      {/* Follow-up action */}
      <section className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-3">
        <div>
          <h3 className="text-white font-semibold">Follow-up Emails</h3>
          <p className="text-gray-500 text-sm mt-1">
            Auto-draft polite follow-up emails for applications with no reply after 5+ days.
            {emails.followups_sent > 0 && ` (${emails.followups_sent} follow-up(s) sent so far)`}
          </p>
        </div>
        {followupMsg && (
          <p className="text-sm px-4 py-2 rounded-lg bg-blue-950 border border-blue-800 text-blue-300">
            {followupMsg}
          </p>
        )}
        <button
          onClick={triggerFollowup}
          disabled={followingUp}
          className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-semibold px-5 py-2 rounded-lg text-sm transition">
          {followingUp ? 'Checking…' : 'Check & Draft Follow-ups'}
        </button>
      </section>
    </div>
  )
}
