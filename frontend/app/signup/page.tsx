'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import api from '@/lib/api'
import PublicHeader from '@/components/PublicHeader'

type Step = 'form' | 'connect-gmail'

export default function Signup() {
  const router = useRouter()
  const [step, setStep] = useState<Step>('form')
  const [form, setForm] = useState({ name: '', username: '', email: '', password: '', confirmPassword: '' })
  const [creds, setCreds] = useState({ clientId: '', clientSecret: '', redirectUri: 'https://hamzabhatti-job-hunter.hf.space/auth/gmail/callback' })
  const [showSecret, setShowSecret] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  const set = (f: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm(p => ({ ...p, [f]: e.target.value }))

  const setCred = (f: keyof typeof creds) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setCreds(p => ({ ...p, [f]: e.target.value }))

  const handleCredentialsFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (ev) => {
      try {
        const json = JSON.parse(ev.target?.result as string)
        const section = json.web || json.installed
        if (!section) { setError('Unrecognized credentials file format.'); return }
        const redirectUri = Array.isArray(section.redirect_uris) && section.redirect_uris.length > 0
          ? section.redirect_uris[0]
          : creds.redirectUri
        setCreds({ clientId: section.client_id || '', clientSecret: section.client_secret || '', redirectUri })
        setError('')
      } catch {
        setError('Could not parse credentials file. Make sure it is the JSON file from Google Cloud Console.')
      }
    }
    reader.readAsText(file)
    e.target.value = ''
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault(); setError('')
    if (form.password !== form.confirmPassword) { setError('Passwords do not match'); return }
    if (form.password.length < 8) { setError('Password must be at least 8 characters'); return }
    setLoading(true)
    try {
      const res = await api.post('/auth/signup', {
        name: form.name, username: form.username, email: form.email, password: form.password,
      })
      localStorage.setItem('token', res.data.access_token)
      localStorage.setItem('user_name', res.data.name || '')
      setStep('connect-gmail')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Signup failed. Please try again.')
    } finally { setLoading(false) }
  }

  const saveAndConnect = async () => {
    setError('')
    if (!creds.clientId.trim()) { setError('Client ID is required.'); return }
    if (!creds.clientSecret.trim()) { setError('Client Secret is required.'); return }
    if (!creds.redirectUri.trim()) { setError('Redirect URI is required.'); return }
    setSaving(true)
    try {
      await api.post('/auth/gmail/credentials', {
        google_client_id: creds.clientId.trim(),
        google_client_secret: creds.clientSecret.trim(),
        google_redirect_uri: creds.redirectUri.trim(),
      })
      const res = await api.get('/auth/gmail/connect')
      window.location.href = res.data.url
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to connect Gmail. Check your credentials and try again.')
      setSaving(false)
    }
  }

  const inp = "w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 text-sm"

  return (
    <>
      <PublicHeader />
      <main className="min-h-screen px-4 pt-24 pb-16">
        <div className="max-w-lg mx-auto">

          {/* Step indicator */}
          <div className="flex items-center justify-center gap-3 mb-8">
            {(['form', 'connect-gmail'] as Step[]).map((s, i) => (
              <div key={s} className="flex items-center gap-3">
                <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition ${
                  step === s ? 'bg-blue-600 text-white' :
                  (i === 0 && step === 'connect-gmail') ? 'bg-emerald-600 text-white' :
                  'bg-gray-800 text-gray-500'
                }`}>
                  {i === 0 && step === 'connect-gmail' ? '✓' : i + 1}
                </div>
                <span className={`text-xs font-medium ${step === s ? 'text-white' : 'text-gray-600'}`}>
                  {s === 'form' ? 'Account' : 'Connect Gmail'}
                </span>
                {i === 0 && <div className="w-8 h-px bg-gray-700" />}
              </div>
            ))}
          </div>

          {/* ── Step 1: Account ── */}
          {step === 'form' && (
            <>
              <div className="mb-8 text-center">
                <h1 className="text-3xl font-bold text-white">Create your account</h1>
                <p className="text-gray-400 mt-2">Step 1 of 2 — your personal details</p>
              </div>

              <form onSubmit={handleSubmit} className="space-y-5">
                <section className="bg-gray-900 border border-gray-800 rounded-2xl p-5 space-y-4">
                  <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Personal Info</h2>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-sm text-gray-400 mb-1">Full Name</label>
                      <input type="text" required value={form.name} onChange={set('name')} placeholder="Jane Smith" className={inp} />
                    </div>
                    <div>
                      <label className="block text-sm text-gray-400 mb-1">Username</label>
                      <input type="text" required value={form.username} onChange={set('username')} placeholder="janesmith"
                        pattern="[a-zA-Z0-9_]+" title="Letters, numbers, underscores only" className={inp} />
                    </div>
                  </div>
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Email</label>
                    <input type="email" required value={form.email} onChange={set('email')} placeholder="jane@example.com" className={inp} />
                    <p className="text-xs text-gray-600 mt-1">Use your Gmail address — you'll connect it in the next step.</p>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-sm text-gray-400 mb-1">Password</label>
                      <input type="password" required value={form.password} onChange={set('password')} placeholder="Min. 8 characters" className={inp} />
                    </div>
                    <div>
                      <label className="block text-sm text-gray-400 mb-1">Confirm Password</label>
                      <input type="password" required value={form.confirmPassword} onChange={set('confirmPassword')} placeholder="Repeat password" className={inp} />
                    </div>
                  </div>
                </section>

                {error && <div className="bg-red-950 border border-red-800 rounded-lg px-4 py-3 text-red-400 text-sm">{error}</div>}

                <button type="submit" disabled={loading}
                  className="w-full bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-semibold py-3 rounded-xl transition text-lg">
                  {loading ? 'Creating account…' : 'Continue →'}
                </button>

                <p className="text-center text-gray-500 text-sm">
                  Already have an account?{' '}
                  <Link href="/login" className="text-blue-400 hover:underline">Log in</Link>
                </p>
              </form>
            </>
          )}

          {/* ── Step 2: Connect Gmail ── */}
          {step === 'connect-gmail' && (
            <>
              <div className="mb-8 text-center">
                <h1 className="text-3xl font-bold text-white">Connect Gmail</h1>
                <p className="text-gray-400 mt-2">Step 2 of 2 — enter your Google OAuth credentials</p>
              </div>

              <div className="space-y-5">

                {/* How to get credentials */}
                <section className="bg-gray-900 border border-gray-800 rounded-2xl p-5 space-y-4">
                  <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">How to get your credentials</h2>
                  <ol className="space-y-2.5 text-sm">
                    {[
                      <>Go to <span className="text-blue-400">console.cloud.google.com</span> → create a project named <span className="bg-gray-800 px-1.5 py-0.5 rounded font-mono text-xs text-gray-200">ApplyAI</span></>,
                      <>Enable <span className="text-white font-medium">Gmail API</span>: APIs & Services → Library → search Gmail API → Enable</>,
                      <>Configure consent screen: APIs & Services → OAuth consent screen → External → fill App name → add scopes <span className="bg-gray-800 px-1.5 py-0.5 rounded font-mono text-xs text-green-400">gmail.send</span> and <span className="bg-gray-800 px-1.5 py-0.5 rounded font-mono text-xs text-green-400">gmail.readonly</span> → add your email as test user</>,
                      <>Create credentials: APIs & Services → Credentials → Create Credentials → OAuth client ID → Web application → add redirect URI: <span className="bg-gray-800 px-1.5 py-0.5 rounded font-mono text-xs text-green-400">https://hamzabhatti-job-hunter.hf.space/auth/gmail/callback</span></>,
                      <>Copy the <span className="text-white font-medium">Client ID</span> and <span className="text-white font-medium">Client Secret</span> shown in the dialog and paste below</>,
                    ].map((s, i) => (
                      <li key={i} className="flex gap-3 text-gray-400">
                        <span className="text-blue-500 font-bold flex-shrink-0 w-4">{i + 1}.</span>
                        <span>{s}</span>
                      </li>
                    ))}
                  </ol>
                  <p className="text-xs text-gray-600">
                    Need detailed screenshots? See the <a href="/dashboard/guide#gmail" className="text-blue-500 hover:underline">Setup Guide</a>.
                  </p>
                </section>

                {/* Credentials form */}
                <section className="bg-gray-900 border border-gray-800 rounded-2xl p-5 space-y-4">
                  <div className="flex items-center justify-between">
                    <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Your Google OAuth Credentials</h2>
                    <label className="cursor-pointer text-xs text-blue-400 hover:text-blue-300 transition font-medium">
                      Upload credentials.json
                      <input type="file" accept=".json,application/json" className="hidden" onChange={handleCredentialsFile} />
                    </label>
                  </div>

                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Client ID</label>
                    <input
                      type="text"
                      value={creds.clientId}
                      onChange={setCred('clientId')}
                      placeholder="1234567890-abcdefg.apps.googleusercontent.com"
                      className={inp}
                    />
                  </div>

                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Client Secret</label>
                    <div className="relative">
                      <input
                        type={showSecret ? 'text' : 'password'}
                        value={creds.clientSecret}
                        onChange={setCred('clientSecret')}
                        placeholder="GOCSPX-xxxxxxxxxxxxxxxxxxxx"
                        className={inp + ' pr-16'}
                      />
                      <button
                        type="button"
                        onClick={() => setShowSecret(v => !v)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 text-xs"
                      >
                        {showSecret ? 'Hide' : 'Show'}
                      </button>
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Authorized Redirect URI</label>
                    <input
                      type="text"
                      value={creds.redirectUri}
                      onChange={setCred('redirectUri')}
                      placeholder="https://hamzabhatti-job-hunter.hf.space/auth/gmail/callback"
                      className={inp}
                    />
                    <p className="text-xs text-gray-600 mt-1">Must exactly match the URI you added in Google Cloud Console → Credentials → Authorized redirect URIs.</p>
                  </div>

                  <div className="bg-gray-950 border border-gray-800 rounded-lg px-4 py-3 text-xs text-gray-500 space-y-1">
                    <p className="text-gray-400 font-medium">These are stored securely on your account.</p>
                    <p>They are used only to authorize Gmail on your behalf — never shared or used for anything else.</p>
                  </div>
                </section>

                {error && <div className="bg-red-950 border border-red-800 rounded-lg px-4 py-3 text-red-400 text-sm">{error}</div>}

                <button
                  onClick={saveAndConnect}
                  disabled={saving}
                  className="w-full bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-semibold py-3 rounded-xl transition text-lg flex items-center justify-center gap-2"
                >
                  {saving ? 'Saving & redirecting to Google…' : 'Save & Connect Gmail →'}
                </button>

                <button
                  onClick={() => router.push('/dashboard')}
                  className="w-full text-gray-500 hover:text-gray-300 text-sm py-2 transition"
                >
                  Skip for now — connect later in Settings
                </button>

              </div>
            </>
          )}

        </div>
      </main>
    </>
  )
}
