'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import api from '@/lib/api'

interface Job {
  id: string; job_title: string; company: string; match_score: number
  match_tier: string; location: string; job_url: string; source: string
  portal_type: string; status: string; created_at: string
  matched_skills: string[]; missing_skills: string[]
}

// ── Recruiter Finder — always expanded, shown on every job ────────────────────
function RecruiterFinder({ company, jobUrl }: { company: string; jobUrl: string }) {
  const [copied, setCopied] = useState('')

  const safeCompany = company || 'this company'
  const domainBase = safeCompany.toLowerCase()
    .replace(/\s+(inc|llc|ltd|pvt|limited|technologies|solutions|group)\.?$/i, '')
    .replace(/[^a-z0-9]/g, '')
  const domain = (domainBase.slice(0, 22) || 'company') + '.com'

  const emailPatterns = [
    `hr@${domain}`, `jobs@${domain}`, `careers@${domain}`, `recruit@${domain}`,
  ]

  const copy = (text: string) => {
    navigator.clipboard.writeText(text)
    setCopied(text)
    setTimeout(() => setCopied(''), 2000)
  }

  const companyQ        = encodeURIComponent(safeCompany)
  const googleHR        = `https://www.google.com/search?q=%22${companyQ}%22+recruiter+OR+%22HR+manager%22+email+site%3Alinkedin.com`
  const googleEmail     = `https://www.google.com/search?q=%22${companyQ}%22+%22@${domain}%22+recruiter+OR+HR`
  const linkedinPeople  = `https://www.linkedin.com/search/results/people/?keywords=${companyQ}+HR+recruiter&origin=GLOBAL_SEARCH_HEADER`
  const linkedinCompany = `https://www.linkedin.com/company/${safeCompany.toLowerCase().replace(/[^a-z0-9]/g, '-')}/people/`

  return (
    <div className="mt-3 border-t border-gray-800 pt-3 space-y-3">

      {/* Search links */}
      <div>
        <p className="text-gray-500 text-xs mb-1.5 font-medium">Find recruiter — opens in a new tab:</p>
        <div className="flex flex-wrap gap-2">
          <a href={googleHR} target="_blank" rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs bg-blue-950 border border-blue-800 text-blue-300 hover:bg-blue-900 px-2.5 py-1 rounded-lg transition">
            Google: LinkedIn HR profiles ↗
          </a>
          <a href={googleEmail} target="_blank" rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs bg-blue-950 border border-blue-800 text-blue-300 hover:bg-blue-900 px-2.5 py-1 rounded-lg transition">
            Google: company email ↗
          </a>
          <a href={linkedinPeople} target="_blank" rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs bg-blue-950 border border-blue-800 text-blue-300 hover:bg-blue-900 px-2.5 py-1 rounded-lg transition">
            LinkedIn: HR people ↗
          </a>
          <a href={linkedinCompany} target="_blank" rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs bg-blue-950 border border-blue-800 text-blue-300 hover:bg-blue-900 px-2.5 py-1 rounded-lg transition">
            LinkedIn: company people ↗
          </a>
          {jobUrl && (
            <a href={jobUrl} target="_blank" rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-xs bg-gray-800 border border-gray-700 text-gray-300 hover:bg-gray-700 px-2.5 py-1 rounded-lg transition">
              Job listing ↗
            </a>
          )}
        </div>
      </div>

      {/* Email pattern guesses — click to copy */}
      <div>
        <p className="text-gray-500 text-xs mb-1.5 font-medium">
          Common email patterns — click to copy:
        </p>
        <div className="flex flex-wrap gap-2">
          {emailPatterns.map(e => (
            <button key={e} onClick={() => copy(e)} title="Click to copy"
              className={`text-xs px-2.5 py-1 rounded font-mono border transition ${
                copied === e
                  ? 'bg-emerald-900 border-emerald-700 text-emerald-300'
                  : 'bg-gray-800 border-gray-700 text-gray-300 hover:border-gray-500'
              }`}>
              {copied === e ? '✓ Copied' : e}
            </button>
          ))}
        </div>
        <p className="text-gray-600 text-xs mt-1.5">
          Tip: open the job listing → check the Contact or About page for the real email.
        </p>
      </div>

    </div>
  )
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
  const router = useRouter()
  const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(true)
  const [clearing, setClearing] = useState(false)
  const [confirmClear, setConfirmClear] = useState(false)
  const [clearError, setClearError] = useState('')

  useEffect(() => { fetchJobs() }, [])

  const fetchJobs = async () => {
    try {
      const res = await api.get('/dashboard/jobs')
      setJobs(res.data)
    } catch { router.push('/login') }
    finally { setLoading(false) }
  }

  const clearJobs = async () => {
    setClearing(true)
    setClearError('')
    try {
      await api.delete('/dashboard/jobs/clear')
      setJobs([])
      setConfirmClear(false)
    } catch (err: any) {
      setClearError(err.response?.data?.detail || 'Failed to clear jobs — please try again.')
    } finally {
      setClearing(false)
    }
  }

  if (loading) return <div className="text-gray-400 py-12 text-center">Loading matched jobs…</div>

  return (
    <div className="space-y-5 max-w-4xl">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-white">Matched Jobs</h2>
          <p className="text-gray-500 text-sm mt-1">
            Jobs matched from your last pipeline run, sorted by relevance score. Find the recruiter email and send your draft from{' '}
            <a href="/dashboard/drafts" className="text-blue-400 hover:underline">Application Drafts</a>.
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
          <p className="text-gray-600 text-sm">Go to <span className="text-blue-400">Overview</span> and run the pipeline with your resume to find matching jobs.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {jobs.map(job => (
            <div key={job.id} className="bg-gray-900 border border-gray-800 rounded-xl px-5 py-4">
              <div className="flex items-start justify-between gap-4">

                {/* Job info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-white font-semibold">{job.job_title}</span>
                    {job.match_tier === 'Top Match' ? (
                      <span className="text-xs px-2 py-0.5 rounded-full font-semibold bg-emerald-900 text-emerald-300 border border-emerald-700">
                        Top Match
                      </span>
                    ) : (
                      <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-blue-900 text-blue-300">
                        Good Match
                      </span>
                    )}
                    <span className={`text-xs px-2.5 py-0.5 rounded-full font-medium ${
                      job.status === 'applied' ? 'bg-green-900 text-green-300' :
                      job.status === 'rejected' ? 'bg-red-900 text-red-300' :
                      'bg-gray-800 text-gray-400'
                    }`}>{job.status}</span>
                  </div>
                  <div className="text-gray-400 text-sm mt-1">{job.company} · {job.location}</div>

                  {/* Skill match / gap */}
                  {(job.matched_skills?.length > 0 || job.missing_skills?.length > 0) && (
                    <div className="mt-2 space-y-1">
                      {job.matched_skills?.length > 0 && (
                        <div className="flex flex-wrap gap-1 items-center">
                          <span className="text-gray-600 text-xs shrink-0">Matched:</span>
                          {job.matched_skills.map(s => (
                            <span key={s} className="text-xs bg-emerald-950 text-emerald-400 border border-emerald-800 px-1.5 py-0.5 rounded">
                              {s}
                            </span>
                          ))}
                        </div>
                      )}
                      {job.missing_skills?.length > 0 && (
                        <div className="flex flex-wrap gap-1 items-center">
                          <span className="text-gray-600 text-xs shrink-0">Gaps:</span>
                          {job.missing_skills.map(s => (
                            <span key={s} className="text-xs bg-gray-800 text-gray-500 border border-gray-700 px-1.5 py-0.5 rounded">
                              {s}
                            </span>
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
                      <span className="text-xs bg-gray-800 text-gray-500 px-2 py-0.5 rounded">
                        {SOURCE_LABELS[job.source] || job.source}
                      </span>
                    )}
                    {job.portal_type && job.portal_type !== 'Unknown' && (
                      <span className="text-xs text-gray-500">
                        via <span className="text-gray-400">{job.portal_type}</span>
                      </span>
                    )}
                  </div>
                </div>

                {/* Score + View link */}
                <div className="flex items-center gap-3 flex-shrink-0">
                  <div className="text-center">
                    <div className={`text-2xl font-bold ${
                      job.match_tier === 'Top Match' ? 'text-emerald-400' : 'text-blue-400'
                    }`}>{Math.round(job.match_score)}%</div>
                    <div className="text-gray-600 text-xs">match</div>
                  </div>
                  {job.job_url && (
                    <a href={job.job_url} target="_blank" rel="noopener noreferrer"
                      className="text-sm text-gray-400 hover:text-white border border-gray-700 hover:border-gray-500 px-3 py-1.5 rounded-lg transition text-center">
                      View
                    </a>
                  )}
                </div>
              </div>

              {/* Recruiter finder — always visible on every job */}
              <RecruiterFinder company={job.company || ''} jobUrl={job.job_url || ''} />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
