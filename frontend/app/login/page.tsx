'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import api from '@/lib/api'
import PublicHeader from '@/components/PublicHeader'

export default function Login() {
  const router = useRouter()
  const [form, setForm] = useState({ email: '', password: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true); setError('')
    try {
      const res = await api.post('/auth/login', { email: form.email, password: form.password })
      localStorage.setItem('token', res.data.access_token)
      localStorage.setItem('user_name', res.data.name || '')
      router.push('/dashboard')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Invalid email or password')
    } finally { setLoading(false) }
  }

  return (
    <>
      <PublicHeader />
      <main className="min-h-screen flex items-center justify-center px-4 pt-16">
        <div className="w-full max-w-md">
          <div className="mb-8 text-center">
            <h1 className="text-3xl font-bold text-white">Welcome back</h1>
            <p className="text-gray-400 mt-2">Log in to continue automating your applications</p>
          </div>

          <form onSubmit={handleSubmit} className="bg-gray-900 border border-gray-800 rounded-2xl p-7 space-y-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">Email</label>
              <input type="email" required value={form.email}
                onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                placeholder="jane@example.com"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500" />
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-1">Password</label>
              <input type="password" required value={form.password}
                onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                placeholder="Your password"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500" />
            </div>

            {error && (
              <div className="bg-red-950 border border-red-800 rounded-lg px-4 py-3 text-red-400 text-sm">{error}</div>
            )}

            <button type="submit" disabled={loading}
              className="w-full bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-semibold py-3 rounded-lg transition">
              {loading ? 'Logging in…' : 'Log In'}
            </button>

            <p className="text-center text-gray-500 text-sm">
              No account?{' '}
              <Link href="/signup" className="text-blue-400 hover:underline">Create one free</Link>
            </p>
          </form>
        </div>
      </main>
    </>
  )
}
