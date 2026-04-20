'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import api from '@/lib/api'

interface Draft {
  id: string; job_id: string | null; draft_content: string; status: string; created_at: string
}
interface Content {
  subject?: string; body?: string; job_title?: string; company?: string; recipient?: string
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
  // Send email state
  const [sendingId, setSendingId] = useState<string | null>(null)
  const [sendEmail, setSendEmail] = useState<Record<string, string>>({})
  const [sendResult, setSendResult] = useState<Record<string, { ok: boolean; msg: string }>>({})
  const [sendLoading, setSendLoading] = useState<string | null>(null)

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

  const toggleSendPanel = (id: string, prefillEmail?: string) => {
    setSendingId(prev => prev === id ? null : id)
    setSendResult(r => ({ ...r, [id]: { ok: false, msg: '' } }))
    if (prefillEmail) {
      setSendEmail(r => ({ ...r, [id]: r[id] || prefillEmail }))
    }
  }

  const sendEmail_ = async (draft: Draft) => {
    const recipient = (sendEmail[draft.id] || '').trim()
    if (!recipient) return
    setSendLoading(draft.id)
    setSendResult(r => ({ ...r, [draft.id]: { ok: false, msg: '' } }))
    try {
      const form = new FormData()
      form.append('recipient_email', recipient)
      await api.post(`/pipeline/send/${draft.id}`, form)
      setSendResult(r => ({ ...r, [draft.id]: { ok: true, msg: `Sent to ${recipient}` } }))
      // Remove from list after short delay
      setTimeout(() => setDrafts(d => d.filter(x => x.id !== draft.id)), 1800)
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Failed to send email'
      setSendResult(r => ({ ...r, [draft.id]: { ok: false, msg } }))
    } finally { setSendLoading(null) }
  }

  if (loading) return <div className="text-gray-400 py-12 text-center">Loading drafts…</div>

  return (
    <div className="space-y-5 max-w-4xl">
      <div>
        <h2 className="text-2xl font-bold text-white">Application Drafts</h2>
        <p className="text-gray-500 text-sm mt-1">
          Copy the email content, or send it directly via your configured SMTP email account.
          <a href="/dashboard/settings" className="text-blue-400 hover:underline ml-1">Set up email →</a>
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
            const result = sendResult[draft.id]
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
                  <div className="flex items-start gap-3">
                    <span className="text-gray-500 text-sm w-16 flex-shrink-0 pt-0.5">Subject</span>
                    <span className="text-gray-200 text-sm font-medium flex-1">{c.subject}</span>
                  </div>
                  <div className="bg-gray-950 border border-gray-800 rounded-lg p-4 text-gray-300 text-sm whitespace-pre-wrap leading-relaxed">
                    {c.body}
                  </div>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-3 px-6 py-4 border-t border-gray-800 bg-gray-950 flex-wrap">
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
                  <button
                    onClick={() => toggleSendPanel(draft.id, c.recipient)}
                    className={`text-sm font-medium px-4 py-2 rounded-lg transition border ${
                      sendingId === draft.id
                        ? 'bg-emerald-900 border-emerald-700 text-emerald-300'
                        : 'bg-gray-800 border-gray-700 text-gray-300 hover:text-white hover:border-emerald-600'
                    }`}>
                    Send via Email
                  </button>
                  <span className="text-gray-600 text-xs ml-auto hidden sm:block">
                    Paste into Gmail, LinkedIn, or the company portal
                  </span>
                </div>

                {/* Send panel */}
                {sendingId === draft.id && (
                  <div className="px-6 py-4 border-t border-gray-800 bg-gray-950 space-y-3">
                    <p className="text-gray-400 text-sm">
                      {c.recipient
                        ? <>Recruiter email pre-filled — verify before sending:</>
                        : <>Enter the recruiter&apos;s email address to send directly:</>}
                    </p>
                    <div className="flex gap-2">
                      <input
                        type="email"
                        placeholder="recruiter@company.com"
                        value={sendEmail[draft.id] || ''}
                        onChange={e => setSendEmail(r => ({ ...r, [draft.id]: e.target.value }))}
                        onKeyDown={e => { if (e.key === 'Enter') sendEmail_(draft) }}
                        className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm placeholder-gray-500 focus:outline-none focus:border-emerald-500"
                      />
                      <button
                        onClick={() => sendEmail_(draft)}
                        disabled={sendLoading === draft.id || !sendEmail[draft.id]?.trim()}
                        className="bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 text-white text-sm font-semibold px-4 py-2 rounded-lg transition">
                        {sendLoading === draft.id ? 'Sending…' : 'Send'}
                      </button>
                    </div>
                    {result?.msg && (
                      <p className={`text-sm ${result.ok ? 'text-emerald-400' : 'text-red-400'}`}>
                        {result.msg}
                        {!result.ok && result.msg.includes('SMTP not configured') && (
                          <a href="/dashboard/settings" className="underline ml-1">Go to Settings</a>
                        )}
                      </p>
                    )}
                    <p className="text-gray-600 text-xs">
                      Requires Gmail (or other SMTP) credentials configured in{' '}
                      <a href="/dashboard/settings" className="text-blue-400 hover:underline">Settings</a>.
                      For Gmail, use an App Password — not your regular password.
                    </p>
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
