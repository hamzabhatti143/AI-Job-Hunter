'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import api from '@/lib/api'
import PublicHeader from '@/components/PublicHeader'

export default function Signup() {
  const router = useRouter()
  const [form, setForm] = useState({ name: '', username: '', email: '', password: '', confirmPassword: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const set = (f: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm(p => ({ ...p, [f]: e.target.value }))

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
      router.push('/dashboard')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Signup failed. Please try again.')
    } finally { setLoading(false) }
  }

  const inp = "w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"

  return (
    <>
      <PublicHeader />
      <main className="min-h-screen px-4 pt-24 pb-16">
        <div className="max-w-md mx-auto">
          <div className="mb-8 text-center">
            <h1 className="text-3xl font-bold text-white">Create your account</h1>
            <p className="text-gray-400 mt-2">Find matching jobs and get ready-to-send application emails</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Personal Info */}
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

            {error && (
              <div className="bg-red-950 border border-red-800 rounded-lg px-4 py-3 text-red-400 text-sm">{error}</div>
            )}

            <button type="submit" disabled={loading}
              className="w-full bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-semibold py-3 rounded-xl transition text-lg">
              {loading ? 'Creating account…' : 'Create Account'}
            </button>

            <p className="text-center text-gray-500 text-sm">
              Already have an account?{' '}
              <Link href="/login" className="text-blue-400 hover:underline">Log in</Link>
            </p>
          </form>
        </div>
      </main>
    </>
  )
}
