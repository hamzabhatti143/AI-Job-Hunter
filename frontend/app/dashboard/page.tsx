'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import api from '@/lib/api'

interface Summary {
  matched_jobs: number
  applied_jobs: number
  drafts: number
  recent_activity: { event_type: string; detail: any; logged_at: string }[]
}

export default function DashboardPage() {
  const router = useRouter()
  const [summary, setSummary] = useState<Summary | null>(null)
  const [plan, setPlan] = useState<'free' | 'paid'>('free')
  const [form, setForm] = useState({ location: '', role_preference: '', resume: null as File | null, api_key: '', recruiter_email: '' })
  const [running, setRunning] = useState(false)
  const [msg, setMsg] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    const savedKey = localStorage.getItem('api_key') || ''
    const savedPlan = localStorage.getItem('plan') as 'free' | 'paid' || 'free'
    setPlan(savedPlan)
    setForm(f => ({ ...f, api_key: savedKey }))
    fetchSummary()
  }, [])

  const fetchSummary = async () => {
    try {
      const res = await api.get('/dashboard/summary')
      setSummary(res.data)
    } catch { router.push('/login') }
  }

  const handlePlanSwitch = (p: 'free' | 'paid') => {
    setPlan(p)
    localStorage.setItem('plan', p)
    if (p === 'free') setForm(f => ({ ...f, api_key: '' }))
  }

  const handleRun = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.resume) { setError('Please attach your resume'); return }
    if (plan === 'paid' && !form.api_key) { setError('Enter your OpenAI API key for the paid plan'); return }
    setRunning(true); setError(''); setMsg('')

    if (plan === 'paid' && form.api_key) {
      localStorage.setItem('api_key', form.api_key)
    }

    const fd = new FormData()
    fd.append('resume', form.resume)
    fd.append('location', form.location)
    fd.append('role_preference', form.role_preference)
    fd.append('api_key', plan === 'free' ? '' : form.api_key)
    fd.append('recruiter_email', form.recruiter_email)

    try {
      // Start pipeline as background task — returns task_id immediately
      const startRes = await api.post('/pipeline/start', fd)
      const { task_id } = startRes.data

      // Poll for status every 4 seconds
      const poll = async (): Promise<void> => {
        try {
          const statusRes = await api.get(`/pipeline/status/${task_id}`)
          const { status, result } = statusRes.data
          if (status === 'running') {
            setTimeout(poll, 4000)
            return
          }
          if (status === 'done') {
            const d = result || {}
            let info = d.output || 'Pipeline complete!'
            if (d.detected_role) info += ` · Role detected: ${d.detected_role}`
            if (d.google_jobs_tip) info += ` · ${d.google_jobs_tip}`
            setMsg(info)
            fetchSummary()
          } else {
            setError(result?.error || 'Pipeline failed — check backend logs.')
          }
        } catch {
          setError('Lost connection to server. Check that the backend is running.')
        }
        setRunning(false)
      }
      setTimeout(poll, 4000)
    } catch (err: any) {
      const detail = err.response?.data?.detail
      setError(Array.isArray(detail) ? detail.map((d: any) => d.msg).join(', ') :
        typeof detail === 'string' ? detail : 'Pipeline failed — could not start.')
      setRunning(false)
    }
  }

  const statCards = summary ? [
    { label: 'Matched Jobs', value: summary.matched_jobs, color: 'text-blue-400', href: '/dashboard/jobs' },
    { label: 'Applied', value: summary.applied_jobs, color: 'text-green-400', href: '/dashboard/applied' },
    { label: 'Drafts Ready', value: summary.drafts, color: 'text-yellow-400', href: '/dashboard/drafts' },
  ] : []

  return (
    <div className="space-y-8 max-w-4xl">
      {/* Stats */}
      {summary && (
        <div className="grid grid-cols-3 gap-4">
          {statCards.map(s => (
            <Link key={s.label} href={s.href}
              className="bg-gray-900 border border-gray-800 hover:border-gray-700 rounded-xl p-5 transition group">
              <p className="text-gray-500 text-sm">{s.label}</p>
              <p className={`text-4xl font-bold mt-1 ${s.color}`}>{s.value}</p>
              <p className="text-gray-700 text-xs mt-2 group-hover:text-gray-500 transition">View →</p>
            </Link>
          ))}
        </div>
      )}

      {/* Pipeline form */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
        <h2 className="text-xl font-semibold text-white mb-1">Find & Draft Applications</h2>
        <p className="text-gray-500 text-sm mb-5">Upload your resume — we find matching jobs and write the application email content for you.</p>

        {/* Plan toggle */}
        <div className="flex gap-2 mb-5 p-1 bg-gray-800 rounded-lg w-fit">
          <button
            type="button"
            onClick={() => handlePlanSwitch('free')}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition ${
              plan === 'free'
                ? 'bg-green-600 text-white'
                : 'text-gray-400 hover:text-gray-200'
            }`}>
            Free — Gemini AI
          </button>
          <button
            type="button"
            onClick={() => handlePlanSwitch('paid')}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition ${
              plan === 'paid'
                ? 'bg-blue-600 text-white'
                : 'text-gray-400 hover:text-gray-200'
            }`}>
            Paid — OpenAI
          </button>
        </div>

        {/* Plan description */}
        <div className={`text-xs rounded-lg px-3 py-2 mb-4 ${
          plan === 'free'
            ? 'bg-green-950 border border-green-900 text-green-400'
            : 'bg-blue-950 border border-blue-900 text-blue-400'
        }`}>
          {plan === 'free'
            ? 'Free plan uses Gemini 2.5 Flash — no API key needed. Great for getting started.'
            : 'Paid plan uses GPT-4o Mini — provide your OpenAI key. Higher quality output.'}
        </div>

        <form onSubmit={handleRun} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">Location</label>
              <input value={form.location} onChange={e => setForm(f => ({ ...f, location: e.target.value }))}
                required placeholder="Enter city, country, or 'Remote'"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-600 focus:outline-none focus:border-blue-500" />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Role</label>
              <input value={form.role_preference} onChange={e => setForm(f => ({ ...f, role_preference: e.target.value }))}
                required placeholder="Frontend Developer, SEO…"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-blue-500" />
            </div>
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Resume (PDF or DOCX)</label>
            <input type="file" accept=".pdf,.docx,.doc"
              onChange={e => setForm(f => ({ ...f, resume: e.target.files?.[0] || null }))}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-gray-300 file:mr-3 file:py-1 file:px-3 file:rounded file:border-0 file:bg-blue-600 file:text-white file:text-sm file:cursor-pointer" />
          </div>

          {/* Recruiter email — optional manual override */}
          <div>
            <label className="block text-sm text-gray-400 mb-1">Recruiter Email <span className="text-gray-600">(optional — skip if unknown)</span></label>
            <input
              type="email"
              value={form.recruiter_email}
              onChange={e => setForm(f => ({ ...f, recruiter_email: e.target.value }))}
              placeholder="recruiter@company.com"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-600 focus:outline-none focus:border-blue-500"
            />
            <p className="text-gray-600 text-xs mt-1">If left blank, we automatically search for the recruiter&apos;s email across 6 sources.</p>
          </div>

          {/* Key input — only shown for paid plan */}
          {plan === 'paid' && (
            <div>
              <label className="block text-sm text-gray-400 mb-1">OpenAI API Key</label>
              <input type="password" value={form.api_key}
                onChange={e => setForm(f => ({ ...f, api_key: e.target.value }))}
                placeholder="sk-proj-…"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-600 focus:outline-none focus:border-blue-500" />
              <p className="text-gray-600 text-xs mt-1">If OpenAI fails, the system automatically falls back to Gemini.</p>
            </div>
          )}

          {error && <p className="text-red-400 text-sm bg-red-950 border border-red-900 rounded-lg px-4 py-2">{error}</p>}
          {msg && <p className="text-green-400 text-sm bg-green-950 border border-green-900 rounded-lg px-4 py-2">{msg}</p>}

          <button type="submit" disabled={running}
            className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-60 disabled:cursor-not-allowed text-white font-semibold px-6 py-2.5 rounded-lg transition">
            {running && (
              <svg className="animate-spin h-4 w-4 text-white flex-shrink-0" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
              </svg>
            )}
            {running ? 'Searching jobs & drafting emails…' : 'Find Jobs & Draft Emails'}
          </button>

          {running && (
            <div className="bg-gray-800 border border-gray-700 rounded-xl p-5 space-y-3">
              <p className="text-gray-300 text-sm font-medium">Pipeline running — this takes 1–2 minutes while we scan job boards</p>
              <div className="space-y-2">
                {[
                  'Parsing resume…',
                  'Extracting skills, role & location…',
                  'Searching jobs across 9+ sources (Google Jobs, LinkedIn, Rozee.pk…)…',
                  'Scoring & matching jobs…',
                  'Drafting application emails…',
                ].map((step, i) => (
                  <div key={i} className="flex items-center gap-3">
                    <svg className="animate-spin h-3.5 w-3.5 text-blue-400 flex-shrink-0" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                    </svg>
                    <span className="text-gray-400 text-sm">{step}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </form>
      </div>

      {/* Recent activity */}
      {summary?.recent_activity && summary.recent_activity.length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <div className="px-5 py-4 border-b border-gray-800">
            <h2 className="text-white font-semibold">Recent Activity</h2>
          </div>
          <div className="divide-y divide-gray-800">
            {summary.recent_activity.slice(0, 8).map((a, i) => (
              <div key={i} className="px-5 py-3 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="w-2 h-2 bg-blue-500 rounded-full flex-shrink-0" />
                  <span className="text-gray-300 text-sm font-medium">{a.event_type.replace(/_/g, ' ')}</span>
                  {a.detail && <span className="text-gray-600 text-xs hidden md:block">{JSON.stringify(a.detail).slice(0, 60)}</span>}
                </div>
                <span className="text-gray-600 text-xs flex-shrink-0 ml-4">{new Date(a.logged_at).toLocaleString()}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
