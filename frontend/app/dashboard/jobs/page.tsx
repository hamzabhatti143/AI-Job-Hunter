'use client'
import { useEffect, useState, useCallback, useRef } from 'react'
import { useRouter } from 'next/navigation'
import api from '@/lib/api'

interface Job {
  id: string; job_title: string; company: string; match_score: number
  match_tier: string; location: string; job_url: string; source: string
  portal_type: string; status: string; created_at: string
  matched_skills: string[]; missing_skills: string[]
  draft_id: string | null; email_subject: string | null; email_body: string | null
}

interface EmailState {
  stage: 'generating' | 'ready' | 'sending' | 'sent' | 'error'
  draftId: string
  subject: string
  body: string
  to: string
  error: string
  expanded: boolean
  copiedPattern: string
}

const SOURCE_LABELS: Record<string, string> = {
  remoteok: 'RemoteOK', remotive: 'Remotive', weworkremotely: 'We Work Remotely',
  arbeitnow: 'Arbeitnow', findwork: 'Findwork', jobicy: 'Jobicy',
  themuse: 'The Muse', serpapi_google_jobs: 'Google Jobs', adzuna: 'Adzuna',
  smartrecruiters: 'Brightspyre', bayt: 'Bayt.com', rozee: 'Rozee.pk',
  acca_global: 'ACCA Global', trabajo_pk: 'Trabajo.org (PK)', bebee: 'Bebee',
  joinimagine: 'Join Imagine', interviewpal: 'InterviewPal',
}

export default function JobsPage() {
  const router                            = useRouter()
  const [jobs, setJobs]                   = useState<Job[]>([])
  const [loading, setLoading]             = useState(true)
  const [clearing, setClearing]           = useState(false)
  const [confirmClear, setConfirmClear]   = useState(false)
  const [clearError, setClearError]       = useState('')
  const [emailStates, setEmailStates]     = useState<Record<string, EmailState>>({})
  const mountedRef                        = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => { mountedRef.current = false }
  }, [])

  // ── Initialise email state from fetched job data ──────────────────────────
  const initStates = useCallback((fetched: Job[]) => {
    const map: Record<string, EmailState> = {}
    for (const j of fetched) {
      map[j.id] = {
        stage:    j.draft_id ? 'ready' : 'generating',
        draftId:  j.draft_id  || '',
        subject:  j.email_subject || '',
        body:     j.email_body    || '',
        to:       '',
        error:    '',
        expanded: false,
        copiedPattern: '',
      }
    }
    setEmailStates(map)
    return map
  }, [])

  // ── Poll until apply-status is done ──────────────────────────────────────
  const pollStatus = useCallback(async (jobId: string) => {
    for (let i = 0; i < 40; i++) {
      await new Promise(r => setTimeout(r, 3000))
      if (!mountedRef.current) return
      try {
        const res  = await api.get(`/pipeline/apply-status/${jobId}`)
        const task = res.data
        if (task.status === 'done' && task.result) {
          const d = task.result
          setEmailStates(prev => ({
            ...prev,
            [jobId]: {
              ...prev[jobId],
              stage:   'ready',
              draftId: d.draft_id  || '',
              subject: d.subject   || '',
              body:    d.body      || '',
            },
          }))
          return
        }
        if (task.status === 'error') {
          setEmailStates(prev => ({
            ...prev,
            [jobId]: { ...prev[jobId], stage: 'error', error: task.result?.error || 'Generation failed.' },
          }))
          return
        }
      } catch { /* keep polling */ }
    }
    if (mountedRef.current) {
      setEmailStates(prev => ({
        ...prev,
        [jobId]: { ...prev[jobId], stage: 'error', error: 'Timed out. Click Retry.' },
      }))
    }
  }, [])

  // ── Generate draft for one job ────────────────────────────────────────────
  const generateDraft = useCallback(async (jobId: string) => {
    setEmailStates(prev => ({
      ...prev,
      [jobId]: { ...prev[jobId], stage: 'generating', error: '' },
    }))
    try {
      await api.post(`/pipeline/apply-job/${jobId}`)
      await pollStatus(jobId)
    } catch {
      if (mountedRef.current) {
        setEmailStates(prev => ({
          ...prev,
          [jobId]: { ...prev[jobId], stage: 'error', error: 'Could not reach server. Click Retry.' },
        }))
      }
    }
  }, [pollStatus])

  // ── Fetch jobs then auto-generate for all without drafts ─────────────────
  const fetchJobs = useCallback(async () => {
    try {
      const res     = await api.get('/dashboard/jobs')
      const fetched: Job[] = res.data
      setJobs(fetched)
      const states = initStates(fetched)
      // Fire generation for all jobs that have no draft yet
      fetched.forEach(j => {
        if (!states[j.id]?.draftId) generateDraft(j.id)
      })
    } catch { router.push('/login') }
    finally { setLoading(false) }
  }, [initStates, generateDraft, router])

  useEffect(() => { fetchJobs() }, [fetchJobs])

  // ── Send email ────────────────────────────────────────────────────────────
  const handleSend = async (jobId: string) => {
    const es = emailStates[jobId]
    if (!es || !es.draftId || !es.to.trim()) return
    setEmailStates(prev => ({ ...prev, [jobId]: { ...prev[jobId], stage: 'sending', error: '' } }))
    try {
      // Save any edits first
      const updateFd = new FormData()
      updateFd.append('subject', es.subject)
      updateFd.append('body',    es.body)
      await api.put(`/pipeline/draft/${es.draftId}`, updateFd)
      // Send
      const fd = new FormData()
      fd.append('recipient_email', es.to.trim())
      const sendRes = await api.post(`/pipeline/send/${es.draftId}`, fd)
      const resumeAttached: boolean = sendRes.data?.resume_attached ?? true
      setEmailStates(prev => ({
        ...prev,
        [jobId]: {
          ...prev[jobId],
          stage: 'sent',
          error: resumeAttached ? '' : 'Email sent but resume was not attached — re-upload your resume in the pipeline and try again.',
        },
      }))
      setJobs(prev => prev.map(j => j.id === jobId ? { ...j, status: 'applied' } : j))
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Failed to send. Check your SMTP settings.'
      setEmailStates(prev => ({ ...prev, [jobId]: { ...prev[jobId], stage: 'ready', error: msg } }))
    }
  }

  const setField = (jobId: string, field: keyof EmailState, value: string | boolean) =>
    setEmailStates(prev => ({ ...prev, [jobId]: { ...prev[jobId], [field]: value } }))

  const getEmailPatterns = (company: string): string[] => {
    const slug = company.toLowerCase().replace(/[^a-z0-9]/g, '')
    if (!slug) return []
    return [
      `hr@${slug}.com`,
      `jobs@${slug}.com`,
      `careers@${slug}.com`,
      `recruit@${slug}.com`,
    ]
  }

  const copyPattern = (jobId: string, pattern: string) => {
    navigator.clipboard.writeText(pattern).catch(() => {})
    setEmailStates(prev => ({ ...prev, [jobId]: { ...prev[jobId], copiedPattern: pattern } }))
    setTimeout(() => {
      setEmailStates(prev => ({ ...prev, [jobId]: { ...prev[jobId], copiedPattern: '' } }))
    }, 1500)
  }

  const recruiterLinks = (company: string, jobUrl: string) => [
    {
      label: 'Google: LinkedIn HR profiles',
      href: `https://www.google.com/search?q=site:linkedin.com+"${encodeURIComponent(company)}"+"HR"+"recruiter"`,
    },
    {
      label: 'Google: company email',
      href: `https://www.google.com/search?q="${encodeURIComponent(company)}"+"email"+"HR"+"careers"`,
    },
    {
      label: 'LinkedIn: HR people',
      href: `https://www.linkedin.com/search/results/people/?keywords=${encodeURIComponent(`"${company}" recruiter OR "HR manager" OR "talent acquisition"`)}&origin=GLOBAL_SEARCH_HEADER`,
    },
    {
      label: 'LinkedIn: company people',
      href: `https://www.linkedin.com/search/results/people/?keywords=${encodeURIComponent(company)}&origin=GLOBAL_SEARCH_HEADER`,
    },
    ...(jobUrl ? [{ label: 'Job listing', href: jobUrl }] : []),
  ]

  const clearJobs = async () => {
    setClearing(true); setClearError('')
    try {
      await api.delete('/dashboard/jobs/clear')
      setJobs([]); setEmailStates({}); setConfirmClear(false)
    } catch (err: any) {
      setClearError(err.response?.data?.detail || 'Failed to clear.')
    } finally { setClearing(false) }
  }

  if (loading) return <div className="text-gray-400 py-12 text-center">Loading matched jobs…</div>

  return (
    <div className="space-y-5 max-w-4xl">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-white">Matched Jobs</h2>
          <p className="text-gray-500 text-sm mt-1">
            Email drafts are generated automatically. Edit subject and body, enter a recipient, then send.
          </p>
        </div>
        {jobs.length > 0 && (
          <div className="flex items-center gap-2 flex-shrink-0">
            {confirmClear ? (
              <>
                <span className="text-gray-400 text-sm">Remove all {jobs.length} jobs?</span>
                <button onClick={clearJobs} disabled={clearing}
                  className="text-sm bg-red-700 hover:bg-red-600 disabled:opacity-50 text-white px-3 py-1.5 rounded-lg transition font-medium">
                  {clearing ? 'Clearing…' : 'Yes, clear'}
                </button>
                <button onClick={() => setConfirmClear(false)}
                  className="text-sm text-gray-500 hover:text-gray-300 px-3 py-1.5 rounded-lg transition">
                  Cancel
                </button>
              </>
            ) : (
              <button onClick={() => setConfirmClear(true)}
                className="text-sm text-red-400 hover:text-red-300 border border-red-900 hover:border-red-700 px-3 py-1.5 rounded-lg transition">
                Clear All
              </button>
            )}
          </div>
        )}
      </div>

      {clearError && (
        <p className="text-red-400 text-sm bg-red-950 border border-red-900 rounded-lg px-4 py-2">{clearError}</p>
      )}

      {jobs.length === 0 ? (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-12 text-center">
          <p className="text-gray-500 mb-3">No matched jobs yet.</p>
          <p className="text-gray-600 text-sm">Go to <span className="text-blue-400">Overview</span> and run the pipeline to find matching jobs.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {jobs.map(job => {
            const es = emailStates[job.id]
            if (!es) return null
            return (
              <div key={job.id} className="bg-gray-900 border border-gray-800 rounded-xl px-5 py-4">

                {/* ── Job info row ── */}
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-white font-semibold">{job.job_title}</span>
                      {job.match_tier === 'Top Match' ? (
                        <span className="text-xs px-2 py-0.5 rounded-full font-semibold bg-emerald-900 text-emerald-300 border border-emerald-700">Top Match</span>
                      ) : (
                        <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-blue-900 text-blue-300">Good Match</span>
                      )}
                      <span className={`text-xs px-2.5 py-0.5 rounded-full font-medium ${
                        job.status === 'applied' ? 'bg-green-900 text-green-300' :
                        job.status === 'rejected' ? 'bg-red-900 text-red-300' : 'bg-gray-800 text-gray-400'
                      }`}>
                        {job.status === 'applied' ? '✅ Applied' : job.status}
                      </span>
                    </div>
                    <div className="text-gray-400 text-sm mt-1">{job.company} · {job.location}</div>
                    {(job.matched_skills?.length > 0 || job.missing_skills?.length > 0) && (
                      <div className="mt-2 space-y-1">
                        {job.matched_skills?.length > 0 && (
                          <div className="flex flex-wrap gap-1 items-center">
                            <span className="text-gray-600 text-xs shrink-0">Matched:</span>
                            {job.matched_skills.map(s => (
                              <span key={s} className="text-xs bg-emerald-950 text-emerald-400 border border-emerald-800 px-1.5 py-0.5 rounded">{s}</span>
                            ))}
                          </div>
                        )}
                        {job.missing_skills?.length > 0 && (
                          <div className="flex flex-wrap gap-1 items-center">
                            <span className="text-gray-600 text-xs shrink-0">Gaps:</span>
                            {job.missing_skills.map(s => (
                              <span key={s} className="text-xs bg-gray-800 text-gray-500 border border-gray-700 px-1.5 py-0.5 rounded">{s}</span>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                    <div className="flex items-center gap-3 mt-1 flex-wrap">
                      <span className="text-gray-500 text-xs">
                        Matched: <span className="text-gray-400">{new Date(job.created_at).toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' })}</span>
                      </span>
                      {job.source && (
                        <span className="text-xs bg-gray-800 text-gray-500 px-2 py-0.5 rounded">{SOURCE_LABELS[job.source] || job.source}</span>
                      )}
                    </div>
                  </div>

                  {/* Score + View + toggle */}
                  <div className="flex flex-col items-center gap-2 flex-shrink-0">
                    <div className="text-center">
                      <div className={`text-2xl font-bold ${job.match_tier === 'Top Match' ? 'text-emerald-400' : 'text-blue-400'}`}>
                        {Math.round(job.match_score)}%
                      </div>
                      <div className="text-gray-600 text-xs">match</div>
                    </div>
                    {job.job_url && (
                      <a href={job.job_url} target="_blank" rel="noopener noreferrer"
                        className="w-full text-sm text-gray-400 hover:text-white border border-gray-700 hover:border-gray-500 px-3 py-1.5 rounded-lg transition text-center">
                        View
                      </a>
                    )}
                    <button
                      onClick={() => setField(job.id, 'expanded', !es.expanded)}
                      className="w-full text-sm text-blue-400 hover:text-white bg-blue-950 hover:bg-blue-900 border border-blue-800 px-3 py-1.5 rounded-lg transition text-center"
                    >
                      {es.expanded ? '▲ Hide' : '✉ Email'}
                    </button>
                  </div>
                </div>

                {/* ── Inline email section ── */}
                {es.expanded && (
                  <div className="mt-4 border-t border-gray-800 pt-4 space-y-3">

                    {/* Generating */}
                    {es.stage === 'generating' && (
                      <div className="flex items-center gap-3 py-2">
                        <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin flex-shrink-0" />
                        <span className="text-gray-400 text-sm">Generating email draft…</span>
                      </div>
                    )}

                    {/* Error */}
                    {es.stage === 'error' && (
                      <div className="flex items-center gap-3">
                        <p className="text-red-400 text-sm flex-1">{es.error}</p>
                        <button onClick={() => generateDraft(job.id)}
                          className="text-sm bg-blue-700 hover:bg-blue-600 text-white px-3 py-1.5 rounded-lg transition">
                          ↻ Retry
                        </button>
                      </div>
                    )}

                    {/* Sent */}
                    {es.stage === 'sent' && (
                      <div className="space-y-1">
                        <p className="text-emerald-400 text-sm font-medium">✅ Email sent successfully.</p>
                        {es.error && (
                          <p className="text-yellow-400 text-xs">{es.error}</p>
                        )}
                      </div>
                    )}

                    {/* Ready / Sending */}
                    {(es.stage === 'ready' || es.stage === 'sending') && (
                      <>
                        {/* Find recruiter */}
                        <div>
                          <p className="text-gray-500 text-xs font-medium mb-1.5">Find recruiter — opens in a new tab</p>
                          <div className="flex flex-wrap gap-1.5">
                            {recruiterLinks(job.company, job.job_url).map(link => (
                              <a
                                key={link.label}
                                href={link.href}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-xs bg-gray-800 border border-gray-700 text-gray-400 hover:text-white hover:border-gray-500 px-2.5 py-1 rounded-lg transition"
                              >
                                {link.label} ↗
                              </a>
                            ))}
                          </div>
                        </div>

                        {/* Common email patterns */}
                        {getEmailPatterns(job.company).length > 0 && (
                          <div>
                            <p className="text-gray-500 text-xs font-medium mb-1.5">Common email patterns — click to copy</p>
                            <div className="flex flex-wrap gap-1.5">
                              {getEmailPatterns(job.company).map(p => (
                                <button
                                  key={p}
                                  onClick={() => copyPattern(job.id, p)}
                                  className={`text-xs px-2.5 py-1 rounded-lg border transition font-mono ${
                                    es.copiedPattern === p
                                      ? 'bg-emerald-900 border-emerald-700 text-emerald-300'
                                      : 'bg-gray-800 border-gray-700 text-gray-400 hover:text-white hover:border-gray-500'
                                  }`}
                                >
                                  {es.copiedPattern === p ? '✓ copied' : p}
                                </button>
                              ))}
                            </div>
                            <p className="text-gray-600 text-xs mt-2">
                              Tip: open the job listing → check the Contact or About page for the real email.
                            </p>
                          </div>
                        )}

                        {/* To */}
                        <div>
                          <label className="text-gray-500 text-xs font-medium block mb-1">To</label>
                          <input
                            value={es.to}
                            onChange={e => setField(job.id, 'to', e.target.value)}
                            placeholder="recruiter@company.com"
                            disabled={es.stage === 'sending'}
                            className="w-full bg-gray-950 border border-gray-700 focus:border-blue-500 text-white text-sm px-3 py-2 rounded-lg outline-none transition disabled:opacity-50"
                          />
                          {!es.to.trim() && (
                            <p className="text-gray-600 text-xs mt-1">Enter recipient email to send.</p>
                          )}
                        </div>

                        {/* Subject */}
                        <div>
                          <label className="text-gray-500 text-xs font-medium block mb-1">Subject</label>
                          <input
                            value={es.subject}
                            onChange={e => setField(job.id, 'subject', e.target.value)}
                            disabled={es.stage === 'sending'}
                            className="w-full bg-gray-950 border border-gray-700 focus:border-blue-500 text-white text-sm px-3 py-2 rounded-lg outline-none transition disabled:opacity-50"
                          />
                        </div>

                        {/* Body */}
                        <div>
                          <label className="text-gray-500 text-xs font-medium block mb-1">Body</label>
                          <textarea
                            value={es.body}
                            onChange={e => setField(job.id, 'body', e.target.value)}
                            rows={10}
                            disabled={es.stage === 'sending'}
                            className="w-full bg-gray-950 border border-gray-700 focus:border-blue-500 text-white text-sm px-3 py-2 rounded-lg outline-none transition font-mono text-xs leading-relaxed resize-none disabled:opacity-50"
                          />
                        </div>

                        {es.error && (
                          <p className="text-red-400 text-sm">{es.error}</p>
                        )}

                        {/* Actions */}
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => generateDraft(job.id)}
                            disabled={es.stage === 'sending'}
                            className="text-sm text-gray-400 hover:text-white border border-gray-700 hover:border-gray-500 px-3 py-2 rounded-lg transition disabled:opacity-40"
                          >
                            ↻ Regenerate
                          </button>
                          <div className="flex-1" />
                          {es.stage === 'sending' ? (
                            <div className="flex items-center gap-2 text-gray-400 text-sm">
                              <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
                              Sending…
                            </div>
                          ) : (
                            <button
                              onClick={() => handleSend(job.id)}
                              disabled={!es.to.trim() || !es.subject.trim()}
                              className="bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold px-5 py-2 rounded-lg transition"
                            >
                              Send ✉
                            </button>
                          )}
                        </div>
                      </>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
