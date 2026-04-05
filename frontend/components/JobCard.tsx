interface Job {
  id: string; job_title: string; company: string; match_score: number
  location: string; job_url: string; status: string
}

export default function JobCard({ job }: { job: Job }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl px-5 py-4 flex items-center justify-between">
      <div>
        <div className="flex items-center gap-3">
          <span className="text-white font-medium">{job.job_title}</span>
          <span className={`text-xs px-2 py-0.5 rounded-full ${
            job.status === 'applied' ? 'bg-green-900 text-green-300' :
            job.status === 'rejected' ? 'bg-red-900 text-red-300' : 'bg-blue-900 text-blue-300'
          }`}>{job.status}</span>
        </div>
        <div className="text-gray-400 text-sm mt-1">{job.company} · {job.location}</div>
      </div>
      <div className="flex items-center gap-4">
        <div className="text-right">
          <div className="text-2xl font-bold text-blue-400">{job.match_score}%</div>
          <div className="text-gray-500 text-xs">match</div>
        </div>
        {job.job_url && (
          <a href={job.job_url} target="_blank"
            className="text-sm text-gray-400 hover:text-white border border-gray-700 hover:border-gray-500 px-3 py-1.5 rounded-lg transition">
            View
          </a>
        )}
      </div>
    </div>
  )
}
