'use client'
import { useEffect, useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import api from '@/lib/api'

interface Draft {
  id: string; job_id: string | null; draft_content: string; status: string; created_at: string
}
interface Content {
  subject?: string; body?: string; job_title?: string; company?: string; recipient?: string
}
interface DraftState {
  subject: string
  body: string
  to: string
  saving: boolean
  sending: boolean
  sent: boolean
  deleting: boolean
  error: string
  resumeWarning: string
  copied: '' | 'all' | 'body'
}

function parse(raw: string): Content {
  try { return JSON.parse(raw) } catch { return { body: raw } }
}

export default function DraftsPage() {
  const router = useRouter()
  const [drafts, setDrafts]       = useState<Draft[]>([])
  const [loading, setLoading]     = useState(true)
  const [states, setStates]       = useState<Record<string, DraftState>>({})

  const setField = (id: string, patch: Partial<DraftState>) =>
    setStates(prev => ({ ...prev, [id]: { ...prev[id], ...patch } }))

  const fetchDrafts = useCallback(async () => {
    try {
      const res = await api.get('/dashboard/pending')
      const pending: Draft[] = res.data.filter((d: Draft) => d.status === 'pending')
      setDrafts(pending)
      const map: Record<string, DraftState> = {}
      for (const d of pending) {
        const c = parse(d.draft_content)
        map[d.id] = {
          subject: c.subject || '',
          body:    c.body    || '',
          to:      c.recipient || '',
          saving: false, sending: false, sent: false, deleting: false,
          error: '', resumeWarning: '', copied: '',
        }
      }
      setStates(map)
    } catch { router.push('/login') }
    finally { setLoading(false) }
  }, [router])

  useEffect(() => { fetchDrafts() }, [fetchDrafts])

  const saveDraft = async (id: string) => {
    const s = states[id]
    if (!s) return
    setField(id, { saving: true, error: '' })
    try {
      const fd = new FormData()
      fd.append('subject', s.subject)
      fd.append('body',    s.body)
      await api.put(`/pipeline/draft/${id}`, fd)
    } catch (err: any) {
      setField(id, { error: err.response?.data?.detail || 'Failed to save.' })
    } finally {
      setField(id, { saving: false })
    }
  }

  const sendDraft = async (id: string) => {
    const s = states[id]
    if (!s || !s.to.trim()) return
    setField(id, { sending: true, error: '', resumeWarning: '' })
    try {
      // Save edits first
      const putFd = new FormData()
      putFd.append('subject', s.subject)
      putFd.append('body',    s.body)
      await api.put(`/pipeline/draft/${id}`, putFd)
      // Send
      const fd = new FormData()
      fd.append('recipient_email', s.to.trim())
      const res = await api.post(`/pipeline/send/${id}`, fd)
      const resumeAttached: boolean = res.data?.resume_attached ?? true
      setField(id, {
        sending: false,
        sent:    true,
        resumeWarning: resumeAttached ? '' : 'Email sent but resume was not attached — re-upload your resume in the pipeline.',
      })
      setTimeout(() => setDrafts(prev => prev.filter(d => d.id !== id)), 2000)
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Failed to send email.'
      setField(id, { sending: false, error: msg })
    }
  }

  const deleteDraft = async (id: string) => {
    setField(id, { deleting: true })
    try {
      await api.delete(`/pipeline/draft/${id}`)
      setDrafts(prev => prev.filter(d => d.id !== id))
    } catch { setField(id, { deleting: false }) }
  }

  const copyText = async (id: string, type: 'all' | 'body') => {
    const s = states[id]
    if (!s) return
    const text = type === 'all' ? `Subject: ${s.subject}\n\n${s.body}` : s.body
    await navigator.clipboard.writeText(text).catch(() => {})
    setField(id, { copied: type })
    setTimeout(() => setField(id, { copied: '' }), 2000)
  }

  if (loading) return <div className="text-gray-400 py-12 text-center">Loading drafts…</div>

  return (
    <div className="space-y-5 max-w-4xl">
      <div>
        <h2 className="text-2xl font-bold text-white">Application Drafts</h2>
        <p className="text-gray-500 text-sm mt-1">
          Edit the subject and body, enter a recipient, then send directly or copy to paste elsewhere.{' '}
          <a href="/dashboard/settings" className="text-blue-400 hover:underline">Set up email →</a>
        </p>
      </div>

      {drafts.length === 0 ? (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-12 text-center">
          <p className="text-gray-500 mb-2">No drafts yet.</p>
          <p className="text-gray-600 text-sm">Run the pipeline from Overview, or go to <strong className="text-gray-400">Matched Jobs</strong> to generate drafts.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {drafts.map(draft => {
            const s = states[draft.id]
            const c = parse(draft.draft_content)
            if (!s) return null
            return (
              <div key={draft.id} className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">

                {/* Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800">
                  <div>
                    <p className="text-white font-semibold">
                      {c.job_title ? `${c.job_title} @ ${c.company}` : 'Application Email'}
                    </p>
                    <p className="text-gray-500 text-xs mt-0.5">
                      {new Date(draft.created_at).toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' })}
                    </p>
                  </div>
                  <button
                    onClick={() => deleteDraft(draft.id)}
                    disabled={s.deleting}
                    className="text-xs text-gray-600 hover:text-red-400 transition px-2 py-1 rounded">
                    {s.deleting ? '…' : 'Dismiss'}
                  </button>
                </div>

                {/* Sent confirmation */}
                {s.sent ? (
                  <div className="px-6 py-5 space-y-1">
                    <p className="text-emerald-400 text-sm font-medium">✅ Email sent successfully.</p>
                    {s.resumeWarning && (
                      <p className="text-yellow-400 text-xs">{s.resumeWarning}</p>
                    )}
                  </div>
                ) : (
                  <>
                    {/* Editable fields */}
                    <div className="px-6 py-4 space-y-3">

                      {/* To */}
                      <div>
                        <label className="text-gray-500 text-xs font-medium block mb-1">To</label>
                        <input
                          value={s.to}
                          onChange={e => setField(draft.id, { to: e.target.value })}
                          placeholder="recruiter@company.com"
                          disabled={s.sending}
                          className="w-full bg-gray-950 border border-gray-700 focus:border-blue-500 text-white text-sm px-3 py-2 rounded-lg outline-none transition disabled:opacity-50"
                        />
                        {!s.to.trim() && (
                          <p className="text-gray-600 text-xs mt-1">Enter recipient email to send.</p>
                        )}
                      </div>

                      {/* Subject */}
                      <div>
                        <label className="text-gray-500 text-xs font-medium block mb-1">Subject</label>
                        <input
                          value={s.subject}
                          onChange={e => setField(draft.id, { subject: e.target.value })}
                          disabled={s.sending}
                          className="w-full bg-gray-950 border border-gray-700 focus:border-blue-500 text-white text-sm px-3 py-2 rounded-lg outline-none transition disabled:opacity-50"
                        />
                      </div>

                      {/* Body */}
                      <div>
                        <label className="text-gray-500 text-xs font-medium block mb-1">Body</label>
                        <textarea
                          value={s.body}
                          onChange={e => setField(draft.id, { body: e.target.value })}
                          rows={12}
                          disabled={s.sending}
                          className="w-full bg-gray-950 border border-gray-700 focus:border-blue-500 text-white text-sm px-3 py-2 rounded-lg outline-none transition font-mono text-xs leading-relaxed resize-none disabled:opacity-50"
                        />
                      </div>

                      {s.error && (
                        <p className="text-red-400 text-sm">
                          {s.error}
                          {s.error.includes('SMTP') && (
                            <a href="/dashboard/settings" className="underline ml-1">Go to Settings</a>
                          )}
                        </p>
                      )}
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-2 px-6 py-4 border-t border-gray-800 bg-gray-950 flex-wrap">
                      <button
                        onClick={() => copyText(draft.id, 'all')}
                        className="text-sm bg-gray-800 hover:bg-gray-700 text-gray-300 px-3 py-2 rounded-lg transition">
                        {s.copied === 'all' ? '✓ Copied!' : 'Copy Subject + Body'}
                      </button>
                      <button
                        onClick={() => copyText(draft.id, 'body')}
                        className="text-sm bg-gray-800 hover:bg-gray-700 text-gray-300 px-3 py-2 rounded-lg transition">
                        {s.copied === 'body' ? '✓ Copied!' : 'Copy Body'}
                      </button>
                      <button
                        onClick={() => saveDraft(draft.id)}
                        disabled={s.saving || s.sending}
                        className="text-sm text-gray-400 hover:text-white border border-gray-700 hover:border-gray-500 px-3 py-2 rounded-lg transition disabled:opacity-40">
                        {s.saving ? 'Saving…' : 'Save'}
                      </button>
                      <div className="flex-1" />
                      {s.sending ? (
                        <div className="flex items-center gap-2 text-gray-400 text-sm">
                          <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
                          Sending…
                        </div>
                      ) : (
                        <button
                          onClick={() => sendDraft(draft.id)}
                          disabled={!s.to.trim() || !s.subject.trim() || s.saving}
                          className="bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold px-5 py-2 rounded-lg transition">
                          Send ✉
                        </button>
                      )}
                    </div>
                  </>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
