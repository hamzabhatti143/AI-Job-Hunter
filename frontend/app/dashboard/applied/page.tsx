'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import api from '@/lib/api'

interface Job {
  id: string; job_title: string; company: string; match_score: number
  location: string; job_url: string; status: string; created_at: string
}

export default function AppliedPage() {
  const router = useRouter()
  const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get('/dashboard/jobs')
      .then(res => setJobs(res.data.filter((j: Job) => j.status === 'applied')))
      .catch(() => router.push('/login'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="text-gray-400 py-12 text-center">Loading…</div>

  return (
    <div className="space-y-5 max-w-4xl">
      <div>
        <h2 className="text-2xl font-bold text-white">Applied Jobs</h2>
        <p className="text-gray-500 text-sm mt-1">Jobs you have applied to — an email draft was created and sent for approval.</p>
      </div>

      {jobs.length === 0 ? (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-12 text-center text-gray-500">
          No applied jobs yet. Click "Apply" on a matched job to get started.
        </div>
      ) : (
        <div className="space-y-3">
          {jobs.map(job => (
            <div key={job.id} className="bg-gray-900 border border-gray-800 rounded-xl px-5 py-4 flex items-center justify-between gap-4">
              <div>
                <div className="flex items-center gap-3">
                  <span className="text-white font-semibold">{job.job_title}</span>
                  <span className="text-xs px-2.5 py-0.5 rounded-full font-medium bg-green-900 text-green-300">applied</span>
                </div>
                <div className="text-gray-400 text-sm mt-1">{job.company} · {job.location}</div>
                <div className="text-gray-600 text-xs mt-1">Applied {new Date(job.created_at).toLocaleDateString()}</div>
              </div>
              <div className="flex items-center gap-3 flex-shrink-0">
                <div className="text-center">
                  <div className="text-xl font-bold text-green-400">{Math.round(job.match_score)}%</div>
                  <div className="text-gray-600 text-xs">match</div>
                </div>
                {job.job_url && (
                  <a href={job.job_url} target="_blank" rel="noopener noreferrer"
                    className="text-sm text-gray-400 hover:text-white border border-gray-700 hover:border-gray-500 px-3 py-1.5 rounded-lg transition">
                    View
                  </a>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
