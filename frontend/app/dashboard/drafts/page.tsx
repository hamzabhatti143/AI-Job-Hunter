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
interface EmailSuggestion {
  address: string; source: string
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
  findingEmails: boolean
  emailSuggestions: EmailSuggestion[]
}

function parse(raw: string): Content {
  try { return JSON.parse(raw) } catch { return { body: raw } }
}

const SOURCE_LABELS: Record<string, string> = {
  'Google search':               'Google',
  'Hunter.io':                   'Hunter',
  'careers page':                'Careers',
  'contact page':                'Contact',
  'job listing':                 'Listing',
  'LinkedIn':                    'LinkedIn',
  'pattern (hr@/jobs@/careers@)': 'Pattern',
}

function SourceBadge({ source }: { source: string }) {
  const label = SOURCE_LABELS[source] || source
  const colors: Record<string, string> = {
    'Google':   'bg-blue-900 text-blue-300',
    'Hunter':   'bg-purple-900 text-purple-300',
    'Careers':  'bg-emerald-900 text-emerald-300',
    'Contact':  'bg-teal-900 text-teal-300',
    'Listing':  'bg-gray-800 text-gray-400',
    'LinkedIn': 'bg-sky-900 text-sky-300',
    'Pattern':  'bg-yellow-900 text-yellow-300',
  }
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${colors[label] || 'bg-gray-800 text-gray-400'}`}>
      {label}
    </span>
  )
}

export default function DraftsPage() {
  const router = useRouter()
  const [drafts, setDrafts]         = useState<Draft[]>([])
  const [loading, setLoading]       = useState(true)
  const [states, setStates]         = useState<Record<string, DraftState>>({})
  const [bulkSending, setBulkSending] = useState(false)
  const [bulkResult, setBulkResult]   = useState<{ sent: number; total: number } | null>(null)

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
          findingEmails: false, emailSuggestions: [],
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
      const putFd = new FormData()
      putFd.append('subject', s.subject)
      putFd.append('body',    s.body)
      await api.put(`/pipeline/draft/${id}`, putFd)
      const fd = new FormData()
      fd.append('recipient_email', s.to.trim())
      const res = await api.post(`/pipeline/send/${id}`, fd)
      const resumeAttached: boolean = res.data?.resume_attached ?? true
      setField(id, {
        sending: false, sent: true,
        resumeWarning: resumeAttached ? '' : 'Email sent but resume was not attached — re-upload your resume in the pipeline.',
      })
      setTimeout(() => setDrafts(prev => prev.filter(d => d.id !== id)), 2000)
    } catch (err: any) {
      setField(id, { sending: false, error: err.response?.data?.detail || 'Failed to send email.' })
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

  const findEmails = async (draftId: string, jobId: string | null) => {
    if (!jobId) {
      setField(draftId, { error: 'No job linked to this draft.' })
      return
    }
    setField(draftId, { findingEmails: true, emailSuggestions: [], error: '' })
    try {
      const res = await api.post(`/pipeline/find-emails/${jobId}`)
      setField(draftId, { emailSuggestions: res.data.emails || [] })
    } catch (err: any) {
      setField(draftId, { error: err.response?.data?.detail || 'Failed to find emails.' })
    } finally {
      setField(draftId, { findingEmails: false })
    }
  }

  const readyDrafts = drafts.filter(d => {
    const s = states[d.id]
    return s && s.to.trim() && !s.sent
  })

  const bulkSend = async () => {
    if (!readyDrafts.length) return
    setBulkSending(true)
    setBulkResult(null)
    try {
      const items = readyDrafts.map(d => ({
        draft_id: d.id,
        recipient_email: states[d.id].to.trim(),
      }))
      const res = await api.post('/pipeline/bulk-send-emails', { items })
      setBulkResult({ sent: res.data.sent, total: res.data.total })
      // Remove successfully sent drafts
      const sentIds = new Set(
        (res.data.results as any[])
          .filter(r => r.success)
          .map(r => r.draft_id)
      )
      setDrafts(prev => prev.filter(d => !sentIds.has(d.id)))
    } catch (err: any) {
      setBulkResult({ sent: 0, total: readyDrafts.length })
    } finally {
      setBulkSending(false)
    }
  }

  if (loading) return <div className="text-gray-400 py-12 text-center">Loading drafts…</div>

  return (
    <div className="space-y-5 max-w-4xl">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-2xl font-bold text-white">Application Drafts</h2>
          <p className="text-gray-500 text-sm mt-1">
            Use <span className="text-blue-400">Find Emails</span> to auto-discover recruiter addresses, then send individually or all at once.{' '}
            <a href="/dashboard/settings" className="text-blue-400 hover:underline">Set up Gmail →</a>
          </p>
        </div>

        {/* Bulk send button */}
        {drafts.length > 0 && (
          <div className="flex flex-col items-end gap-1">
            <button
              onClick={bulkSend}
              disabled={bulkSending || readyDrafts.length === 0}
              className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold px-5 py-2.5 rounded-xl transition flex items-center gap-2"
            >
              {bulkSending ? (
                <><div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" /> Sending all…</>
              ) : (
                <>Send All ({readyDrafts.length} ready)</>
              )}
            </button>
            {readyDrafts.length === 0 && !bulkSending && (
              <p className="text-gray-600 text-xs">Add recipient emails below to enable bulk send</p>
            )}
            {bulkResult && (
              <p className={`text-xs font-medium ${bulkResult.sent === bulkResult.total ? 'text-emerald-400' : 'text-yellow-400'}`}>
                {bulkResult.sent}/{bulkResult.total} sent successfully
              </p>
            )}
          </div>
        )}
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

                {s.sent ? (
                  <div className="px-6 py-5 space-y-1">
                    <p className="text-emerald-400 text-sm font-medium">✅ Email sent successfully.</p>
                    {s.resumeWarning && <p className="text-yellow-400 text-xs">{s.resumeWarning}</p>}
                  </div>
                ) : (
                  <>
                    <div className="px-6 py-4 space-y-3">

                      {/* To field + Find Emails */}
                      <div>
                        <div className="flex items-center justify-between mb-1">
                          <label className="text-gray-500 text-xs font-medium">To</label>
                          <button
                            onClick={() => findEmails(draft.id, draft.job_id)}
                            disabled={s.findingEmails || s.sending}
                            className="text-xs text-blue-400 hover:text-blue-300 disabled:opacity-50 transition flex items-center gap-1"
                          >
                            {s.findingEmails ? (
                              <><div className="w-3 h-3 border border-blue-400 border-t-transparent rounded-full animate-spin" /> Searching…</>
                            ) : (
                              '🔍 Find Emails'
                            )}
                          </button>
                        </div>
                        <input
                          value={s.to}
                          onChange={e => setField(draft.id, { to: e.target.value })}
                          placeholder="recruiter@company.com"
                          disabled={s.sending}
                          className="w-full bg-gray-950 border border-gray-700 focus:border-blue-500 text-white text-sm px-3 py-2 rounded-lg outline-none transition disabled:opacity-50"
                        />

                        {/* Email suggestions */}
                        {s.emailSuggestions.length > 0 && (
                          <div className="mt-2 space-y-1">
                            <p className="text-gray-600 text-xs">Click an email to use it:</p>
                            <div className="flex flex-wrap gap-2">
                              {s.emailSuggestions.map((suggestion, i) => (
                                <button
                                  key={i}
                                  onClick={() => setField(draft.id, { to: suggestion.address })}
                                  className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs transition ${
                                    s.to === suggestion.address
                                      ? 'bg-blue-600 border-blue-500 text-white'
                                      : 'bg-gray-800 border-gray-700 text-gray-300 hover:border-blue-500 hover:text-white'
                                  }`}
                                >
                                  <span>{suggestion.address}</span>
                                  <SourceBadge source={suggestion.source} />
                                </button>
                              ))}
                            </div>
                          </div>
                        )}

                        {s.emailSuggestions.length === 0 && !s.findingEmails && s.to === '' && (
                          <p className="text-gray-600 text-xs mt-1">Click "Find Emails" to search for recruiter addresses, or type one manually.</p>
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
                        <p className="text-red-400 text-sm">{s.error}</p>
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
