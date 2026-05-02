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
  company: string
  location: string
}

function parse(raw: string): Content {
  try { return JSON.parse(raw) } catch { return { body: raw } }
}

const SOURCE_COLOR: Record<string, string> = {
  'Google search': 'bg-blue-900 border-blue-700 text-blue-300',
  'Hunter.io':     'bg-purple-900 border-purple-700 text-purple-300',
  'careers page':  'bg-emerald-900 border-emerald-700 text-emerald-300',
  'contact page':  'bg-teal-900 border-teal-700 text-teal-300',
  'job listing':   'bg-gray-800 border-gray-600 text-gray-300',
  'LinkedIn':      'bg-sky-900 border-sky-700 text-sky-300',
  'pattern':       'bg-yellow-900 border-yellow-700 text-yellow-300',
}
const SOURCE_LABEL: Record<string, string> = {
  'Google search': 'Google',
  'Hunter.io':     'Hunter',
  'careers page':  'Careers',
  'contact page':  'Contact',
  'job listing':   'Listing',
  'LinkedIn':      'LinkedIn',
  'pattern':       'Pattern',
}

function SourceTag({ source }: { source: string }) {
  const cls = SOURCE_COLOR[source] || 'bg-gray-800 border-gray-600 text-gray-400'
  const lbl = SOURCE_LABEL[source] || source
  return <span className={`text-[9px] px-1 py-0.5 rounded border font-semibold uppercase tracking-wide ${cls}`}>{lbl}</span>
}

export default function DraftsPage() {
  const router = useRouter()
  const [drafts, setDrafts]   = useState<Draft[]>([])
  const [loading, setLoading] = useState(true)
  const [states, setStates]   = useState<Record<string, DraftState>>({})

  // Bulk-discover state
  const [discovering, setDiscovering]     = useState(false)
  const [discoverDone, setDiscoverDone]   = useState(0)
  const [discoverTotal, setDiscoverTotal] = useState(0)

  // Bulk-send state
  const [bulkSending, setBulkSending]   = useState(false)
  const [bulkResult, setBulkResult]     = useState<{ sent: number; total: number } | null>(null)

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
          subject: c.subject || '', body: c.body || '', to: c.recipient || '',
          saving: false, sending: false, sent: false, deleting: false,
          error: '', resumeWarning: '', copied: '',
          findingEmails: false, emailSuggestions: [], company: '', location: '',
        }
      }
      setStates(map)
    } catch { router.push('/login') }
    finally { setLoading(false) }
  }, [router])

  useEffect(() => { fetchDrafts() }, [fetchDrafts])

  // ── Discover emails for one draft ──────────────────────────────────────────
  const findEmails = async (draftId: string, jobId: string | null) => {
    if (!jobId) { setField(draftId, { error: 'No job linked to this draft.' }); return }
    setField(draftId, { findingEmails: true, emailSuggestions: [], error: '' })
    try {
      const res = await api.post(`/pipeline/find-emails/${jobId}`)
      setField(draftId, {
        emailSuggestions: res.data.emails || [],
        company:  res.data.company  || '',
        location: res.data.location || '',
      })
    } catch (err: any) {
      setField(draftId, { error: err.response?.data?.detail || 'Failed to find emails.' })
    } finally {
      setField(draftId, { findingEmails: false })
    }
  }

  // ── Discover emails for ALL drafts at once ─────────────────────────────────
  const discoverAll = async () => {
    setDiscovering(true)
    setDiscoverDone(0)
    setDiscoverTotal(drafts.length)
    setBulkResult(null)

    // Mark all as searching
    setStates(prev => {
      const next = { ...prev }
      for (const d of drafts) next[d.id] = { ...next[d.id], findingEmails: true, emailSuggestions: [], error: '' }
      return next
    })

    try {
      const res = await api.post('/pipeline/discover-all-emails')
      const results: Array<{ draft_id: string; company: string; location: string; emails: EmailSuggestion[] }> =
        res.data.results || []

      setDiscoverDone(results.length)
      setStates(prev => {
        const next = { ...prev }
        for (const r of results) {
          if (next[r.draft_id]) {
            next[r.draft_id] = {
              ...next[r.draft_id],
              findingEmails:    false,
              emailSuggestions: r.emails || [],
              company:          r.company  || next[r.draft_id].company,
              location:         r.location || next[r.draft_id].location,
              // Auto-select first non-pattern email if To is still empty
              to: next[r.draft_id].to || (r.emails?.find(e => e.source !== 'pattern')?.address ?? r.emails?.[0]?.address ?? ''),
            }
          }
        }
        return next
      })
    } catch (err: any) {
      // Clear searching state on error
      setStates(prev => {
        const next = { ...prev }
        for (const d of drafts) next[d.id] = { ...next[d.id], findingEmails: false }
        return next
      })
    } finally {
      setDiscovering(false)
    }
  }

  // ── Individual send ────────────────────────────────────────────────────────
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
      setField(id, {
        sending: false, sent: true,
        resumeWarning: res.data?.resume_attached ? '' : 'Sent but resume not attached — re-upload in pipeline.',
      })
      setTimeout(() => setDrafts(prev => prev.filter(d => d.id !== id)), 2000)
    } catch (err: any) {
      setField(id, { sending: false, error: err.response?.data?.detail || 'Failed to send.' })
    }
  }

  // ── Bulk send all drafts that have a To address ────────────────────────────
  const readyDrafts = drafts.filter(d => states[d.id]?.to?.trim() && !states[d.id]?.sent)

  const bulkSend = async () => {
    if (!readyDrafts.length) return
    setBulkSending(true)
    setBulkResult(null)
    try {
      const items = readyDrafts.map(d => ({ draft_id: d.id, recipient_email: states[d.id].to.trim() }))
      const res = await api.post('/pipeline/bulk-send-emails', { items })
      setBulkResult({ sent: res.data.sent, total: res.data.total })
      const sentIds = new Set((res.data.results as any[]).filter(r => r.success).map(r => r.draft_id))
      setDrafts(prev => prev.filter(d => !sentIds.has(d.id)))
    } catch {
      setBulkResult({ sent: 0, total: readyDrafts.length })
    } finally {
      setBulkSending(false)
    }
  }

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
    } finally { setField(id, { saving: false }) }
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

      {/* ── Top bar ── */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-2xl font-bold text-white">Application Drafts</h2>
          <p className="text-gray-500 text-sm mt-1">
            Discover recruiter emails from Google, then send individually or all at once.{' '}
            <a href="/dashboard/settings" className="text-blue-400 hover:underline">Set up Gmail →</a>
          </p>
        </div>

        {drafts.length > 0 && (
          <div className="flex flex-col items-end gap-2">
            {/* Discover All button */}
            <button
              onClick={discoverAll}
              disabled={discovering || bulkSending}
              className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold px-4 py-2.5 rounded-xl transition flex items-center gap-2"
            >
              {discovering ? (
                <><div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Searching {discoverDone}/{discoverTotal}…</>
              ) : '🔍 Discover All Emails'}
            </button>

            {/* Send All button */}
            <button
              onClick={bulkSend}
              disabled={bulkSending || discovering || readyDrafts.length === 0}
              className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold px-4 py-2.5 rounded-xl transition flex items-center gap-2"
            >
              {bulkSending ? (
                <><div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" /> Sending…</>
              ) : `✉ Send All (${readyDrafts.length} ready)`}
            </button>

            {readyDrafts.length === 0 && !discovering && (
              <p className="text-gray-600 text-xs text-right">Discover emails first, then Send All</p>
            )}
            {bulkResult && (
              <p className={`text-xs font-medium ${bulkResult.sent === bulkResult.total ? 'text-emerald-400' : 'text-yellow-400'}`}>
                {bulkResult.sent}/{bulkResult.total} sent successfully
              </p>
            )}
          </div>
        )}
      </div>

      {/* ── Empty state ── */}
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

            const company  = s.company  || c.company  || ''
            const location = s.location || ''

            return (
              <div key={draft.id} className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">

                {/* Card header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800">
                  <div>
                    <p className="text-white font-semibold">
                      {c.job_title ? `${c.job_title}` : 'Application Email'}
                      {company ? <span className="text-gray-400 font-normal"> @ {company}</span> : null}
                    </p>
                    <div className="flex items-center gap-2 mt-0.5">
                      {location && (
                        <span className="text-gray-600 text-xs">📍 {location}</span>
                      )}
                      <span className="text-gray-600 text-xs">
                        {new Date(draft.created_at).toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' })}
                      </span>
                    </div>
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

                      {/* To field */}
                      <div>
                        <div className="flex items-center justify-between mb-1">
                          <label className="text-gray-500 text-xs font-medium">To</label>
                          <button
                            onClick={() => findEmails(draft.id, draft.job_id)}
                            disabled={s.findingEmails || s.sending}
                            className="text-xs text-blue-400 hover:text-blue-300 disabled:opacity-50 transition flex items-center gap-1"
                          >
                            {s.findingEmails
                              ? <><div className="w-3 h-3 border border-blue-400 border-t-transparent rounded-full animate-spin" /> Searching…</>
                              : '🔍 Find Emails'}
                          </button>
                        </div>

                        <input
                          value={s.to}
                          onChange={e => setField(draft.id, { to: e.target.value })}
                          placeholder="recruiter@company.com"
                          disabled={s.sending}
                          className="w-full bg-gray-950 border border-gray-700 focus:border-blue-500 text-white text-sm px-3 py-2 rounded-lg outline-none transition disabled:opacity-50"
                        />

                        {/* Email suggestion chips */}
                        {s.emailSuggestions.length > 0 && (
                          <div className="mt-2 space-y-1.5">
                            <p className="text-gray-600 text-xs">
                              {s.emailSuggestions.length} email{s.emailSuggestions.length > 1 ? 's' : ''} found — click to use:
                            </p>
                            <div className="flex flex-wrap gap-1.5">
                              {s.emailSuggestions.map((sg, i) => (
                                <button
                                  key={i}
                                  onClick={() => setField(draft.id, { to: sg.address })}
                                  title={`Source: ${sg.source}`}
                                  className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs transition ${
                                    s.to === sg.address
                                      ? 'bg-blue-600 border-blue-500 text-white'
                                      : 'bg-gray-800 border-gray-700 text-gray-300 hover:border-blue-500 hover:text-white'
                                  }`}
                                >
                                  {sg.address}
                                  <SourceTag source={sg.source} />
                                </button>
                              ))}
                            </div>
                          </div>
                        )}

                        {s.emailSuggestions.length === 0 && !s.findingEmails && !s.to && (
                          <p className="text-gray-600 text-xs mt-1">
                            Click "Find Emails" or "Discover All Emails" to search Google for recruiter addresses.
                          </p>
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

                      {s.error && <p className="text-red-400 text-sm">{s.error}</p>}
                    </div>

                    {/* Action bar */}
                    <div className="flex items-center gap-2 px-6 py-4 border-t border-gray-800 bg-gray-950 flex-wrap">
                      <button onClick={() => copyText(draft.id, 'all')}
                        className="text-sm bg-gray-800 hover:bg-gray-700 text-gray-300 px-3 py-2 rounded-lg transition">
                        {s.copied === 'all' ? '✓ Copied!' : 'Copy Subject + Body'}
                      </button>
                      <button onClick={() => copyText(draft.id, 'body')}
                        className="text-sm bg-gray-800 hover:bg-gray-700 text-gray-300 px-3 py-2 rounded-lg transition">
                        {s.copied === 'body' ? '✓ Copied!' : 'Copy Body'}
                      </button>
                      <button onClick={() => saveDraft(draft.id)} disabled={s.saving || s.sending}
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
