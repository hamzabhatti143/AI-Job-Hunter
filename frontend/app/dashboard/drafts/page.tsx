'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import api from '@/lib/api'

interface Draft {
  id: string; job_id: string | null; draft_content: string; status: string; created_at: string
}
interface Content {
  subject?: string; body?: string; job_title?: string; company?: string
}
function parse(raw: string): Content {
  try { return JSON.parse(raw) } catch { return { body: raw } }
}

export default function DraftsPage() {
  const router = useRouter()
  const [drafts, setDrafts] = useState<Draft[]>([])
  const [loading, setLoading] = useState(true)
  const [copied, setCopied] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<string | null>(null)

  useEffect(() => { fetchDrafts() }, [])

  const fetchDrafts = async () => {
    try {
      const res = await api.get('/dashboard/pending')
      setDrafts(res.data.filter((d: Draft) => d.status === 'pending'))
    } catch { router.push('/login') }
    finally { setLoading(false) }
  }

  const copyAll = async (draft: Draft) => {
    const c = parse(draft.draft_content)
    const text = `Subject: ${c.subject || ''}\n\n${c.body || ''}`
    await navigator.clipboard.writeText(text)
    setCopied(draft.id)
    setTimeout(() => setCopied(null), 2500)
  }

  const copyBody = async (draft: Draft) => {
    const c = parse(draft.draft_content)
    await navigator.clipboard.writeText(c.body || '')
    setCopied(draft.id + '_body')
    setTimeout(() => setCopied(null), 2500)
  }

  const deleteDraft = async (draft: Draft) => {
    setDeleting(draft.id)
    try {
      await api.delete(`/pipeline/draft/${draft.id}`)
      setDrafts(d => d.filter(x => x.id !== draft.id))
    } catch { } finally { setDeleting(null) }
  }

  if (loading) return <div className="text-gray-400 py-12 text-center">Loading drafts…</div>

  return (
    <div className="space-y-5 max-w-4xl">
      <div>
        <h2 className="text-2xl font-bold text-white">Application Drafts</h2>
        <p className="text-gray-500 text-sm mt-1">
          Copy the email content below and send it yourself to the recruiter — via Gmail, LinkedIn, or the company's careers page.
        </p>
      </div>

      {drafts.length === 0 ? (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-12 text-center">
          <p className="text-gray-500 mb-2">No drafts yet.</p>
          <p className="text-gray-600 text-sm">Run the pipeline from Overview, or click <strong className="text-gray-400">Apply</strong> on a matched job.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {drafts.map(draft => {
            const c = parse(draft.draft_content)
            return (
              <div key={draft.id} className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800">
                  <div>
                    <p className="text-white font-semibold">
                      {c.job_title ? `${c.job_title} @ ${c.company}` : 'Application Email'}
                    </p>
                    <p className="text-gray-500 text-xs mt-0.5">{new Date(draft.created_at).toLocaleString()}</p>
                  </div>
                  <button
                    onClick={() => deleteDraft(draft)}
                    disabled={deleting === draft.id}
                    className="text-xs text-gray-600 hover:text-red-400 transition px-2 py-1 rounded">
                    {deleting === draft.id ? '…' : 'Dismiss'}
                  </button>
                </div>

                {/* Content */}
                <div className="px-6 py-4 space-y-3">
                  {/* Subject line */}
                  <div className="flex items-start gap-3">
                    <span className="text-gray-500 text-sm w-16 flex-shrink-0 pt-0.5">Subject</span>
                    <div className="flex-1 flex items-center gap-2">
                      <span className="text-gray-200 text-sm font-medium flex-1">{c.subject}</span>
                    </div>
                  </div>

                  {/* Email body */}
                  <div className="bg-gray-950 border border-gray-800 rounded-lg p-4 text-gray-300 text-sm whitespace-pre-wrap leading-relaxed">
                    {c.body}
                  </div>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-3 px-6 py-4 border-t border-gray-800 bg-gray-950">
                  <button
                    onClick={() => copyAll(draft)}
                    className="bg-blue-700 hover:bg-blue-600 text-white text-sm font-semibold px-4 py-2 rounded-lg transition">
                    {copied === draft.id ? 'Copied!' : 'Copy Subject + Body'}
                  </button>
                  <button
                    onClick={() => copyBody(draft)}
                    className="bg-gray-800 hover:bg-gray-700 text-gray-300 text-sm font-medium px-4 py-2 rounded-lg transition">
                    {copied === draft.id + '_body' ? 'Copied!' : 'Copy Body Only'}
                  </button>
                  <span className="text-gray-600 text-xs ml-auto">Paste this into Gmail, LinkedIn, or the company portal</span>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
