'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import api from '@/lib/api'

export default function SettingsPage() {
  const router = useRouter()
  const [form, setForm] = useState({
    smtp_host: '', smtp_port: '587', smtp_user: '', smtp_password: ''
  })
  const [configured, setConfigured] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [showPass, setShowPass] = useState(false)
  const [result, setResult] = useState<{ ok: boolean; msg: string } | null>(null)

  useEffect(() => {
    api.get('/auth/smtp-settings')
      .then(res => {
        setForm({
          smtp_host: res.data.smtp_host || '',
          smtp_port: String(res.data.smtp_port || 587),
          smtp_user: res.data.smtp_user || '',
          smtp_password: '',
        })
        setConfigured(res.data.smtp_configured)
      })
      .catch(() => router.push('/login'))
      .finally(() => setLoading(false))
  }, [])

  const set = (f: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm(p => ({ ...p, [f]: e.target.value }))

  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setResult(null)
    try {
      await api.put('/auth/smtp-settings', {
        smtp_host: form.smtp_host,
        smtp_port: parseInt(form.smtp_port) || 587,
        smtp_user: form.smtp_user,
        smtp_password: form.smtp_password,
      })
      setConfigured(!!form.smtp_host && !!form.smtp_user && !!form.smtp_password)
      setResult({ ok: true, msg: 'SMTP settings saved successfully.' })
    } catch (err: any) {
      setResult({ ok: false, msg: err.response?.data?.detail || 'Failed to save settings.' })
    } finally { setSaving(false) }
  }

  const inp = "w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 text-sm"

  if (loading) return <div className="text-gray-400 py-12 text-center">Loading settings…</div>

  return (
    <div className="max-w-xl space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white">Settings</h2>
        <p className="text-gray-500 text-sm mt-1">Configure your email account to send application emails directly from the Drafts page.</p>
      </div>

      {/* Status badge */}
      <div className={`flex items-center gap-2 px-4 py-3 rounded-lg border text-sm ${
        configured ? 'bg-emerald-950 border-emerald-800 text-emerald-400' : 'bg-gray-900 border-gray-800 text-gray-500'
      }`}>
        <span className={`w-2 h-2 rounded-full ${configured ? 'bg-emerald-400' : 'bg-gray-600'}`} />
        {configured ? 'Email sending is configured and ready.' : 'Email sending is not configured yet.'}
      </div>

      <form onSubmit={save} className="bg-gray-900 border border-gray-800 rounded-2xl p-6 space-y-5">
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">SMTP Email Configuration</h3>

        {/* Help note */}
        <div className="bg-blue-950 border border-blue-800 rounded-lg px-4 py-3 text-blue-300 text-xs space-y-1">
          <p><strong>Gmail users:</strong> Use <code className="bg-blue-900 px-1 rounded">smtp.gmail.com</code> as host, port <code className="bg-blue-900 px-1 rounded">587</code>, and an <strong>App Password</strong> (not your regular password).</p>
          <p>Generate an App Password at: Google Account → Security → 2-Step Verification → App passwords.</p>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="col-span-2 sm:col-span-1">
            <label className="block text-sm text-gray-400 mb-1">SMTP Host</label>
            <input type="text" value={form.smtp_host} onChange={set('smtp_host')}
              placeholder="smtp.gmail.com" className={inp} />
          </div>
          <div className="col-span-2 sm:col-span-1">
            <label className="block text-sm text-gray-400 mb-1">Port</label>
            <input type="number" value={form.smtp_port} onChange={set('smtp_port')}
              placeholder="587" className={inp} />
          </div>
        </div>

        <div>
          <label className="block text-sm text-gray-400 mb-1">Your Email Address</label>
          <input type="email" value={form.smtp_user} onChange={set('smtp_user')}
            placeholder="you@gmail.com" className={inp} />
        </div>

        <div>
          <label className="block text-sm text-gray-400 mb-1">
            {configured ? 'App Password (leave blank to keep current)' : 'App Password'}
          </label>
          <div className="relative">
            <input
              type={showPass ? 'text' : 'password'}
              value={form.smtp_password}
              onChange={set('smtp_password')}
              placeholder={configured ? '••••••••••••' : 'xxxx xxxx xxxx xxxx'}
              className={inp + ' pr-16'}
            />
            <button
              type="button"
              onClick={() => setShowPass(v => !v)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 text-xs">
              {showPass ? 'Hide' : 'Show'}
            </button>
          </div>
        </div>

        {result && (
          <div className={`px-4 py-3 rounded-lg border text-sm ${
            result.ok ? 'bg-emerald-950 border-emerald-800 text-emerald-400' : 'bg-red-950 border-red-800 text-red-400'
          }`}>
            {result.msg}
          </div>
        )}

        <div className="flex items-center gap-3 pt-1">
          <button
            type="submit"
            disabled={saving}
            className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-semibold px-6 py-2.5 rounded-xl transition text-sm">
            {saving ? 'Saving…' : 'Save Settings'}
          </button>
          {configured && (
            <button
              type="button"
              onClick={async () => {
                setSaving(true)
                try {
                  await api.put('/auth/smtp-settings', { smtp_host: '', smtp_port: 587, smtp_user: '', smtp_password: '' })
                  setForm({ smtp_host: '', smtp_port: '587', smtp_user: '', smtp_password: '' })
                  setConfigured(false)
                  setResult({ ok: true, msg: 'SMTP settings cleared.' })
                } catch { setResult({ ok: false, msg: 'Failed to clear settings.' }) }
                finally { setSaving(false) }
              }}
              disabled={saving}
              className="text-sm text-gray-500 hover:text-red-400 px-3 py-2.5 rounded-xl transition">
              Clear
            </button>
          )}
        </div>
      </form>
    </div>
  )
}
