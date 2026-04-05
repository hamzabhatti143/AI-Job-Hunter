'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import api from '@/lib/api'

interface SentEmail {
  id: string; recipient_email: string; email_content: string
  resume_attached: boolean; sent_at: string; job_id: string
}
interface EmailContent {
  subject?: string; body?: string; job_title?: string; company?: string
}
function parse(raw: string): EmailContent {
  try { return JSON.parse(raw) } catch { return { body: raw } }
}

export default function SentPage() {
  const router = useRouter()
  const [emails, setEmails] = useState<SentEmail[]>([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<string | null>(null)

  useEffect(() => {
    api.get('/dashboard/data/sent')
      .then(res => setEmails(res.data))
      .catch(() => router.push('/login'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="text-gray-400 py-12 text-center">Loading…</div>

  return (
    <div className="space-y-5 max-w-4xl">
      <div>
        <h2 className="text-2xl font-bold text-white">Sent Emails</h2>
        <p className="text-gray-500 text-sm mt-1">All application emails that have been sent to recruiters.</p>
      </div>

      {emails.length === 0 ? (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-12 text-center text-gray-500">
          No emails sent yet. Approve a pending email to send it.
        </div>
      ) : (
        <div className="space-y-3">
          {emails.map(e => {
            const content = parse(e.email_content)
            const isOpen = expanded === e.id
            return (
              <div key={e.id} className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
                <button onClick={() => setExpanded(isOpen ? null : e.id)}
                  className="w-full flex items-center justify-between px-5 py-4 text-left hover:bg-gray-800/50 transition">
                  <div>
                    <p className="text-white font-semibold">
                      {content.job_title ? `${content.job_title} @ ${content.company}` : e.recipient_email}
                    </p>
                    <p className="text-gray-500 text-sm mt-0.5">To: {e.recipient_email} · {new Date(e.sent_at).toLocaleString()}</p>
                  </div>
                  <div className="flex items-center gap-3 flex-shrink-0">
                    {e.resume_attached && (
                      <span className="text-xs bg-gray-700 text-gray-300 px-2 py-0.5 rounded">Resume attached</span>
                    )}
                    <span className="text-gray-500 text-sm">{isOpen ? '▲' : '▼'}</span>
                  </div>
                </button>
                {isOpen && (
                  <div className="border-t border-gray-800 px-5 py-4 space-y-3">
                    <div className="grid grid-cols-[72px_1fr] gap-2 text-sm">
                      <span className="text-gray-500">To</span>
                      <span className="text-gray-300">{e.recipient_email}</span>
                      <span className="text-gray-500">Subject</span>
                      <span className="text-gray-200 font-medium">{content.subject || '—'}</span>
                    </div>
                    <div className="bg-gray-950 border border-gray-800 rounded-lg p-4 text-gray-300 text-sm whitespace-pre-wrap leading-relaxed">
                      {content.body || e.email_content}
                    </div>
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
