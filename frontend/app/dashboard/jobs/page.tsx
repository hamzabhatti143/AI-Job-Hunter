'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import api from '@/lib/api'

interface Job {
  id: string; job_title: string; company: string; match_score: number
  location: string; job_url: string; status: string; created_at: string
}

export default function JobsPage() {
  const router = useRouter()
  const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(true)
  const [applying, setApplying] = useState<string | null>(null)
  const [msg, setMsg] = useState<{ id: string; text: string; type: 'ok' | 'err' } | null>(null)
  const [apiKeyPrompt, setApiKeyPrompt] = useState<{ jobId: string; key: string } | null>(null)
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

  const applyJob = async (job: Job, overrideKey?: string) => {
    const apiKey = overrideKey || localStorage.getItem('api_key') || ''
    if (!apiKey) {
      setApiKeyPrompt({ jobId: job.id, key: '' })
      return
    }
    // Save key for future use
    localStorage.setItem('api_key', apiKey)
    setApiKeyPrompt(null)
    setApplying(job.id)
    setMsg(null)
    const fd = new FormData()
    fd.append('api_key', apiKey)
    try {
      await api.post(`/pipeline/apply-job/${job.id}`, fd)
      setMsg({ id: job.id, text: `Email drafted for ${job.job_title}! Check Pending Emails to approve and send.`, type: 'ok' })
      fetchJobs()
    } catch (err: any) {
      const detail = err.response?.data?.detail
      let errorText = 'Failed to apply — please try again.'
      if (typeof detail === 'string') {
        errorText = detail
      } else if (Array.isArray(detail)) {
        errorText = detail.map((d: any) => d.msg || d.message || JSON.stringify(d)).join('; ')
      } else if (detail) {
        errorText = JSON.stringify(detail)
      }
      setMsg({ id: job.id, text: errorText, type: 'err' })
    } finally {
      setApplying(null)
    }
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
          <p className="text-gray-500 text-sm mt-1">Jobs matched from your last pipeline run, sorted by relevance score.</p>
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
                  <div className="flex items-center gap-3 flex-wrap">
                    <span className="text-white font-semibold">{job.job_title}</span>
                    <span className={`text-xs px-2.5 py-0.5 rounded-full font-medium ${
                      job.status === 'applied' ? 'bg-green-900 text-green-300' :
                      job.status === 'rejected' ? 'bg-red-900 text-red-300' :
                      'bg-blue-900 text-blue-300'
                    }`}>{job.status}</span>
                  </div>
                  <div className="text-gray-400 text-sm mt-1">{job.company} · {job.location}</div>
                  <div className="text-gray-500 text-xs mt-1">
                    Matched on: <span className="text-gray-400">{new Date(job.created_at).toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' })}</span>
                  </div>
                </div>

                {/* Score + actions */}
                <div className="flex items-center gap-3 flex-shrink-0">
                  <div className="text-center">
                    <div className={`text-2xl font-bold ${
                      job.match_score >= 70 ? 'text-green-400' :
                      job.match_score >= 50 ? 'text-blue-400' : 'text-yellow-400'
                    }`}>{Math.round(job.match_score)}%</div>
                    <div className="text-gray-600 text-xs">match</div>
                  </div>
                  <div className="flex flex-col gap-2">
                    {job.job_url && (
                      <a href={job.job_url} target="_blank" rel="noopener noreferrer"
                        className="text-sm text-gray-400 hover:text-white border border-gray-700 hover:border-gray-500 px-3 py-1.5 rounded-lg transition text-center">
                        View
                      </a>
                    )}
                    {job.status === 'matched' && (
                      <button
                        onClick={() => applyJob(job)}
                        disabled={applying === job.id}
                        className="text-sm bg-blue-700 hover:bg-blue-600 disabled:opacity-50 text-white px-3 py-1.5 rounded-lg transition font-medium">
                        {applying === job.id ? 'Working…' : 'Apply'}
                      </button>
                    )}
                  </div>
                </div>
              </div>

              {/* API key prompt */}
              {apiKeyPrompt && apiKeyPrompt.jobId === job.id && (
                <div className="mt-3 bg-gray-800 border border-gray-700 rounded-lg p-4">
                  <p className="text-gray-300 text-sm mb-2 font-medium">Enter your OpenAI API key to generate the application email:</p>
                  <div className="flex gap-2">
                    <input
                      type="password"
                      value={apiKeyPrompt.key}
                      onChange={e => setApiKeyPrompt(p => p ? { ...p, key: e.target.value } : null)}
                      placeholder="sk-proj-…"
                      className="flex-1 bg-gray-700 border border-gray-600 rounded-lg px-3 py-1.5 text-white text-sm placeholder-gray-500 focus:outline-none focus:border-blue-500"
                    />
                    <button
                      onClick={() => { if (apiKeyPrompt.key) applyJob(job, apiKeyPrompt.key) }}
                      disabled={!apiKeyPrompt.key}
                      className="bg-blue-700 hover:bg-blue-600 disabled:opacity-50 text-white text-sm px-4 py-1.5 rounded-lg transition font-medium">
                      Apply
                    </button>
                    <button
                      onClick={() => setApiKeyPrompt(null)}
                      className="text-gray-500 hover:text-gray-300 text-sm px-3 py-1.5 rounded-lg transition">
                      Cancel
                    </button>
                  </div>
                  <p className="text-gray-600 text-xs mt-1">Your key is saved locally in this browser for future use.</p>
                </div>
              )}

              {/* Feedback messages */}
              {msg && msg.id === job.id && (
                <div className={`mt-3 text-sm px-3 py-2 rounded-lg ${
                  msg.type === 'ok'
                    ? 'bg-green-950 border border-green-800 text-green-300'
                    : 'bg-red-950 border border-red-800 text-red-300'
                }`}>
                  {msg.text}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
