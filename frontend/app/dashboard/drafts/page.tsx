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
  selectedEmails: string[]      // multi-select for bulk send
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
  'email prefix':    'bg-blue-900 border-blue-700 text-blue-300',
  'recruiter search':'bg-blue-900 border-blue-700 text-blue-300',
  'HR search':       'bg-indigo-900 border-indigo-700 text-indigo-300',
  'hiring manager':  'bg-indigo-900 border-indigo-700 text-indigo-300',
  'domain search':   'bg-emerald-900 border-emerald-700 text-emerald-300',
  'application email':'bg-teal-900 border-teal-700 text-teal-300',
  'LinkedIn':        'bg-sky-900 border-sky-700 text-sky-300',
  'recent search':   'bg-blue-900 border-blue-700 text-blue-300',
  'Google search':   'bg-blue-900 border-blue-700 text-blue-300',
  'page scrape':     'bg-gray-800 border-gray-600 text-gray-300',
  'Hunter.io':       'bg-purple-900 border-purple-700 text-purple-300',
  'careers page':    'bg-emerald-900 border-emerald-700 text-emerald-300',
  'contact page':    'bg-teal-900 border-teal-700 text-teal-300',
  'job listing':     'bg-gray-800 border-gray-600 text-gray-300',
  'pattern':         'bg-yellow-900 border-yellow-700 text-yellow-300',
}
const SOURCE_LABEL: Record<string, string> = {
  'email prefix':    'Prefix',
  'recruiter search':'Recruiter',
  'HR search':       'HR',
  'hiring manager':  'HiringMgr',
  'domain search':   'Domain',
  'application email':'Apply',
  'LinkedIn':        'LinkedIn',
  'recent search':   'Recent',
  'Google search':   'Google',
  'page scrape':     'Scraped',
  'Hunter.io':       'Hunter',
  'careers page':    'Careers',
  'contact page':    'Contact',
  'job listing':     'Listing',
  'pattern':         'Pattern',
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
  const [bulkTaskId, setBulkTaskId]     = useState<string | null>(null)
  const [bulkProgress, setBulkProgress] = useState<{ sent: number; total: number; done: boolean; skipped?: number; eta?: number } | null>(null)

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
          selectedEmails: [],
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

  // ── Send to multiple selected emails at once ─────────────────────────────
  const sendDraftMulti = async (id: string, emails: string[]) => {
    if (!emails.length) return
    setField(id, { sending: true, error: '', resumeWarning: '' })
    try {
      // Save latest subject/body first
      const s = states[id]
      const putFd = new FormData()
      putFd.append('subject', s.subject)
      putFd.append('body',    s.body)
      await api.put(`/pipeline/draft/${id}`, putFd)

      // Queue as bulk send — each email gets its own send with 60s gap
      const items = emails.map(email => ({ draft_id: id, recipient_email: email }))
      const res = await api.post('/pipeline/bulk-send-emails', { items })
      const { task_id, queued, skipped } = res.data

      if (!task_id) {
        setField(id, { sending: false, error: `All ${emails.length} emails were skipped (rate limit).` })
        return
      }

      // Poll until done
      const poll = setInterval(async () => {
        try {
          const status = await api.get(`/pipeline/bulk-send-status/${task_id}`)
          const d = status.data
          if (d.status === 'done' || d.status === 'error') {
            clearInterval(poll)
            const sentCount = (d.results as any[]).filter((r: any) => r.success).length
            setField(id, {
              sending: false,
              sent: sentCount > 0,
              resumeWarning: sentCount < emails.length ? `${sentCount}/${emails.length} sent (others rate-limited)` : '',
            })
            if (sentCount > 0) setTimeout(() => setDrafts(prev => prev.filter(dd => dd.id !== id)), 2000)
          }
        } catch { clearInterval(poll); setField(id, { sending: false }) }
      }, 10_000)
    } catch (err: any) {
      setField(id, { sending: false, error: err.response?.data?.detail || 'Failed to send.' })
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
    setBulkTaskId(null)
    setBulkProgress(null)
    try {
      const items = readyDrafts.map(d => ({ draft_id: d.id, recipient_email: states[d.id].to.trim() }))
      const res = await api.post('/pipeline/bulk-send-emails', { items })
      const { task_id, queued, skipped, eta_seconds } = res.data

      if (!task_id) {
        // All filtered — nothing to send
        setBulkProgress({ sent: 0, total: 0, done: true, skipped: skipped?.length ?? 0 })
        setBulkSending(false)
        return
      }

      setBulkTaskId(task_id)
      setBulkProgress({ sent: 0, total: queued, done: false, skipped: skipped?.length ?? 0, eta: eta_seconds })

      // Poll every 15s until done
      const poll = setInterval(async () => {
        try {
          const status = await api.get(`/pipeline/bulk-send-status/${task_id}`)
          const d = status.data
          const sentCount = (d.results as any[])?.filter((r: any) => r.success).length ?? 0
          setBulkProgress(prev => ({ ...(prev ?? { total: queued, skipped: 0 }), sent: sentCount, done: d.status === 'done', eta: undefined }))

          if (d.status === 'done' || d.status === 'error') {
            clearInterval(poll)
            setBulkSending(false)
            const sentIds = new Set((d.results as any[]).filter((r: any) => r.success).map((r: any) => r.draft_id))
            setDrafts(prev => prev.filter(dd => !sentIds.has(dd.id)))
          }
        } catch {
          clearInterval(poll)
          setBulkSending(false)
        }
      }, 15_000)
    } catch (err: any) {
      const detail = err.response?.data?.detail || 'Failed to queue bulk send.'
      setBulkProgress({ sent: 0, total: readyDrafts.length, done: true, skipped: 0 })
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
                <><div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  {bulkProgress && !bulkProgress.done ? `Sending ${bulkProgress.sent}/${bulkProgress.total}…` : 'Queuing…'}
                </>
              ) : `✉ Send All (${readyDrafts.length} ready)`}
            </button>

            {readyDrafts.length === 0 && !discovering && (
              <p className="text-gray-600 text-xs text-right">Discover emails first, then Send All</p>
            )}
            {bulkProgress && (
              <div className="text-xs text-right space-y-0.5">
                {!bulkProgress.done ? (
                  <p className="text-indigo-300 font-medium animate-pulse">
                    Sending… {bulkProgress.sent}/{bulkProgress.total}
                    {bulkProgress.eta ? ` · ~${Math.ceil(bulkProgress.eta / 60)}min remaining` : ''}
                  </p>
                ) : (
                  <p className={`font-medium ${bulkProgress.sent === bulkProgress.total && bulkProgress.total > 0 ? 'text-emerald-400' : 'text-yellow-400'}`}>
                    {bulkProgress.sent}/{bulkProgress.total} sent
                    {bulkProgress.skipped ? ` · ${bulkProgress.skipped} skipped (rate limit)` : ''}
                  </p>
                )}
              </div>
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

                        {/* Email suggestion chips — multi-select */}
                        {s.emailSuggestions.length > 0 && (
                          <div className="mt-3 space-y-2">
                            <div className="flex items-center justify-between">
                              <p className="text-gray-400 text-xs font-medium">
                                {s.emailSuggestions.length} email{s.emailSuggestions.length !== 1 ? 's' : ''} found
                                {s.selectedEmails.length > 0 && (
                                  <span className="ml-2 text-indigo-400">· {s.selectedEmails.length} selected</span>
                                )}
                              </p>
                              <div className="flex gap-2">
                                <button
                                  onClick={() => setField(draft.id, { selectedEmails: s.emailSuggestions.map(e => e.address) })}
                                  className="text-[10px] text-indigo-400 hover:text-indigo-300 transition">
                                  Select all
                                </button>
                                <button
                                  onClick={() => setField(draft.id, { selectedEmails: [], to: '' })}
                                  className="text-[10px] text-gray-600 hover:text-gray-400 transition">
                                  Clear
                                </button>
                              </div>
                            </div>

                            <div className="flex flex-wrap gap-1.5">
                              {s.emailSuggestions.map((sg, i) => {
                                const isSelected = s.selectedEmails.includes(sg.address)
                                const isFilled   = s.to === sg.address
                                return (
                                  <button
                                    key={i}
                                    title={`Source: ${sg.source} — click to fill To field, Ctrl+click to multi-select`}
                                    onClick={(e) => {
                                      if (e.ctrlKey || e.metaKey) {
                                        // Ctrl+click → toggle multi-select
                                        const next = isSelected
                                          ? s.selectedEmails.filter(x => x !== sg.address)
                                          : [...s.selectedEmails, sg.address]
                                        setField(draft.id, { selectedEmails: next })
                                      } else {
                                        // Normal click → fill To field + select
                                        const next = isSelected
                                          ? s.selectedEmails.filter(x => x !== sg.address)
                                          : [...s.selectedEmails, sg.address]
                                        setField(draft.id, { to: sg.address, selectedEmails: next })
                                      }
                                    }}
                                    className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs transition ${
                                      isSelected
                                        ? 'bg-indigo-700 border-indigo-500 text-white'
                                        : isFilled
                                          ? 'bg-blue-600 border-blue-500 text-white'
                                          : 'bg-gray-800 border-gray-700 text-gray-300 hover:border-indigo-500 hover:text-white'
                                    }`}
                                  >
                                    {isSelected && <span className="text-indigo-300">✓</span>}
                                    {sg.address}
                                    <SourceTag source={sg.source} />
                                  </button>
                                )
                              })}
                            </div>

                            {/* Multi-send bar — appears when 2+ emails selected */}
                            {s.selectedEmails.length >= 2 && (
                              <div className="flex items-center gap-2 mt-1 p-2 bg-indigo-950 border border-indigo-800 rounded-lg">
                                <span className="text-indigo-300 text-xs flex-1">
                                  Send to {s.selectedEmails.length} addresses: {s.selectedEmails.slice(0,2).join(', ')}{s.selectedEmails.length > 2 ? ` +${s.selectedEmails.length - 2} more` : ''}
                                </span>
                                <button
                                  onClick={() => sendDraftMulti(draft.id, s.selectedEmails)}
                                  disabled={s.sending}
                                  className="text-xs bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white px-3 py-1.5 rounded-lg font-medium transition"
                                >
                                  {s.sending ? 'Sending…' : `Send to ${s.selectedEmails.length}`}
                                </button>
                              </div>
                            )}
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
