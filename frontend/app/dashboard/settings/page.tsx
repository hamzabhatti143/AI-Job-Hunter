'use client'
import { Suspense } from 'react'
import { useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import api from '@/lib/api'

function SettingsInner() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [gmailConnected, setGmailConnected] = useState(false)
  const [creds, setCreds] = useState({ clientId: '', clientSecret: '', redirectUri: 'https://hamzabhatti-job-hunter.hf.space/auth/gmail/callback' })
  const [showSecret, setShowSecret] = useState(false)
  const [loading, setLoading] = useState(true)
  const [connecting, setConnecting] = useState(false)
  const [disconnecting, setDisconnecting] = useState(false)
  const [banner, setBanner] = useState<{ ok: boolean; msg: string } | null>(null)

  useEffect(() => {
    const gmailParam = searchParams.get('gmail')
    if (gmailParam === 'connected') setBanner({ ok: true,  msg: 'Gmail connected successfully.' })
    if (gmailParam === 'error')     setBanner({ ok: false, msg: 'Gmail connection failed. Please try again.' })
    if (gmailParam === 'expired')   setBanner({ ok: false, msg: 'Connection timed out. Please try again.' })
    if (gmailParam) router.replace('/dashboard/settings')
  }, [])

  useEffect(() => {
    Promise.all([
      api.get('/auth/me'),
      api.get('/auth/gmail/status'),
    ]).then(([me, gmail]) => {
      setEmail(me.data.email || '')
      setName(me.data.name || '')
      setGmailConnected(gmail.data.connected || false)
    }).catch(() => router.push('/login'))
      .finally(() => setLoading(false))
  }, [])

  const handleCredentialsFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (ev) => {
      try {
        const json = JSON.parse(ev.target?.result as string)
        const section = json.web || json.installed
        if (!section) { setBanner({ ok: false, msg: 'Unrecognized credentials file format.' }); return }
        const redirectUri = Array.isArray(section.redirect_uris) && section.redirect_uris.length > 0
          ? section.redirect_uris[0]
          : creds.redirectUri
        setCreds({ clientId: section.client_id || '', clientSecret: section.client_secret || '', redirectUri })
        setBanner(null)
      } catch {
        setBanner({ ok: false, msg: 'Could not parse credentials file. Make sure it is the JSON file from Google Cloud Console.' })
      }
    }
    reader.readAsText(file)
    e.target.value = ''
  }

  const connectGmail = async () => {
    setBanner(null)
    if (!creds.clientId.trim() || !creds.clientSecret.trim() || !creds.redirectUri.trim()) {
      setBanner({ ok: false, msg: 'Client ID, Client Secret, and Redirect URI are all required.' })
      return
    }
    setConnecting(true)
    try {
      await api.post('/auth/gmail/credentials', {
        google_client_id: creds.clientId.trim(),
        google_client_secret: creds.clientSecret.trim(),
        google_redirect_uri: creds.redirectUri.trim(),
      })
      const res = await api.get('/auth/gmail/connect')
      window.location.href = res.data.url
    } catch (err: any) {
      setBanner({ ok: false, msg: err.response?.data?.detail || 'Failed to start Gmail connection.' })
      setConnecting(false)
    }
  }

  const disconnectGmail = async () => {
    setDisconnecting(true)
    setBanner(null)
    try {
      await api.delete('/auth/gmail/disconnect')
      setGmailConnected(false)
      setBanner({ ok: true, msg: 'Gmail disconnected.' })
    } catch {
      setBanner({ ok: false, msg: 'Failed to disconnect Gmail.' })
    } finally { setDisconnecting(false) }
  }

  if (loading) return <div className="text-gray-400 py-12 text-center">Loading settings…</div>

  return (
    <div className="max-w-xl space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white">Settings</h2>
        <p className="text-gray-500 text-sm mt-1">Your account details and email configuration.</p>
      </div>

      {banner && (
        <div className={`px-4 py-3 rounded-lg border text-sm ${
          banner.ok ? 'bg-emerald-950 border-emerald-800 text-emerald-400' : 'bg-red-950 border-red-800 text-red-400'
        }`}>
          {banner.msg}
        </div>
      )}

      {/* Account */}
      <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 space-y-4">
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">Account</h3>
        <div className="space-y-1 text-sm">
          <div className="flex justify-between items-center py-2 border-b border-gray-800">
            <span className="text-gray-400">Name</span>
            <span className="text-white font-medium">{name}</span>
          </div>
          <div className="flex justify-between items-center py-2">
            <span className="text-gray-400">Email</span>
            <span className="text-white font-medium">{email}</span>
          </div>
        </div>
      </div>

      {/* Gmail */}
      <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 space-y-5">
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">Gmail — Email Sending</h3>

        {/* Status badge */}
        <div className={`flex items-center gap-2 px-4 py-3 rounded-lg border text-sm ${
          gmailConnected
            ? 'bg-emerald-950 border-emerald-800 text-emerald-400'
            : 'bg-gray-950 border-gray-700 text-gray-500'
        }`}>
          <span className={`w-2 h-2 rounded-full flex-shrink-0 ${gmailConnected ? 'bg-emerald-400' : 'bg-gray-600'}`} />
          {gmailConnected
            ? `Gmail connected — emails sent from ${email}`
            : 'Gmail not connected — connect to start sending application emails'}
        </div>

        {gmailConnected ? (
          <div className="space-y-4">
            <div className="divide-y divide-gray-800 rounded-xl overflow-hidden border border-gray-800 text-sm">
              <div className="bg-gray-950 px-5 py-3 grid grid-cols-5 gap-4">
                <div className="col-span-2 text-white font-medium">FROM address</div>
                <div className="col-span-3 text-gray-400 text-xs flex items-center">{email} — your own Gmail, looks personal to recruiters</div>
              </div>
              <div className="bg-gray-950 px-5 py-3 grid grid-cols-5 gap-4">
                <div className="col-span-2 text-white font-medium">Reply tracking</div>
                <div className="col-span-3 text-gray-400 text-xs flex items-center">Automatic — recruiter replies appear in Sent Emails when you visit the page</div>
              </div>
            </div>

            <button
              onClick={disconnectGmail}
              disabled={disconnecting}
              className="text-sm text-gray-500 hover:text-red-400 transition disabled:opacity-50"
            >
              {disconnecting ? 'Disconnecting…' : 'Disconnect Gmail'}
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500">Enter manually or upload your credentials file</span>
                <label className="cursor-pointer text-xs text-blue-400 hover:text-blue-300 transition font-medium">
                  Upload credentials.json
                  <input type="file" accept=".json,application/json" className="hidden" onChange={handleCredentialsFile} />
                </label>
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Google Client ID</label>
                <input
                  type="text"
                  value={creds.clientId}
                  onChange={e => setCreds(p => ({ ...p, clientId: e.target.value }))}
                  placeholder="1234567890-abc.apps.googleusercontent.com"
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 text-sm"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Google Client Secret</label>
                <div className="relative">
                  <input
                    type={showSecret ? 'text' : 'password'}
                    value={creds.clientSecret}
                    onChange={e => setCreds(p => ({ ...p, clientSecret: e.target.value }))}
                    placeholder="GOCSPX-xxxxxxxxxxxxxxxxxxxx"
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 text-sm pr-16"
                  />
                  <button type="button" onClick={() => setShowSecret(v => !v)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 text-xs">
                    {showSecret ? 'Hide' : 'Show'}
                  </button>
                </div>
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Authorized Redirect URI</label>
                <input
                  type="text"
                  value={creds.redirectUri}
                  onChange={e => setCreds(p => ({ ...p, redirectUri: e.target.value }))}
                  placeholder="https://hamzabhatti-job-hunter.hf.space/auth/gmail/callback"
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 text-sm"
                />
                <p className="text-xs text-gray-600 mt-1">Must exactly match the URI registered in Google Cloud Console.</p>
              </div>
            </div>

            <div className="bg-blue-950 border border-blue-800 rounded-lg px-4 py-3 text-blue-300 text-xs space-y-1">
              <p className="font-medium text-blue-200">Where to get these</p>
              <p>Go to <span className="text-white">console.cloud.google.com</span> → create a project → enable Gmail API → OAuth consent screen → Credentials → Create OAuth client ID (Web application). See the <a href="/dashboard/guide#gmail" className="underline">Setup Guide</a> for full steps.</p>
            </div>

            <button
              onClick={connectGmail}
              disabled={connecting}
              className="w-full bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-semibold py-2.5 rounded-xl transition text-sm"
            >
              {connecting ? 'Saving & redirecting to Google…' : 'Save & Connect Gmail'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

export default function SettingsPage() {
  return (
    <Suspense fallback={<div className="text-gray-400 py-12 text-center">Loading settings…</div>}>
      <SettingsInner />
    </Suspense>
  )
}
