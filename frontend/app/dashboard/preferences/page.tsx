'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import api from '@/lib/api'

interface Prefs {
  preferred_roles: string
  preferred_locations: string
  salary_min: number | null
  salary_max: number | null
  job_type: string
  open_to_remote: boolean
}

export default function PreferencesPage() {
  const router = useRouter()
  const [form, setForm] = useState<Prefs>({
    preferred_roles: '', preferred_locations: '',
    salary_min: null, salary_max: null,
    job_type: 'full-time', open_to_remote: true,
  })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [result, setResult] = useState<{ ok: boolean; msg: string } | null>(null)

  useEffect(() => {
    api.get('/dashboard/preferences')
      .then(res => {
        const d = res.data
        if (d && Object.keys(d).length > 0) {
          setForm({
            preferred_roles:     d.preferred_roles || '',
            preferred_locations: d.preferred_locations || '',
            salary_min:          d.salary_min ?? null,
            salary_max:          d.salary_max ?? null,
            job_type:            d.job_type || 'full-time',
            open_to_remote:      d.open_to_remote ?? true,
          })
        }
      })
      .catch(() => router.push('/login'))
      .finally(() => setLoading(false))
  }, [])

  const inp = "w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 text-sm"

  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setResult(null)
    try {
      const params = new URLSearchParams()
      params.set('preferred_roles', form.preferred_roles)
      params.set('preferred_locations', form.preferred_locations)
      if (form.salary_min) params.set('salary_min', String(form.salary_min))
      if (form.salary_max) params.set('salary_max', String(form.salary_max))
      params.set('job_type', form.job_type)
      params.set('open_to_remote', String(form.open_to_remote))
      await api.post(`/dashboard/preferences?${params.toString()}`)
      setResult({ ok: true, msg: 'Preferences saved. They will be applied on your next pipeline run.' })
    } catch (err: any) {
      setResult({ ok: false, msg: err.response?.data?.detail || 'Failed to save preferences.' })
    } finally { setSaving(false) }
  }

  if (loading) return <div className="text-gray-400 py-12 text-center">Loading preferences…</div>

  return (
    <div className="max-w-xl space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white">Job Preferences</h2>
        <p className="text-gray-500 text-sm mt-1">
          Pre-fill your search preferences so you don&apos;t need to re-enter them every session.
          Salary filters and job type are applied automatically during the pipeline run.
        </p>
      </div>

      <form onSubmit={save} className="bg-gray-900 border border-gray-800 rounded-2xl p-6 space-y-5">
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">Search Defaults</h3>

        <div>
          <label className="block text-sm text-gray-400 mb-1">
            Preferred Roles <span className="text-gray-600">(comma-separated)</span>
          </label>
          <input type="text" value={form.preferred_roles}
            onChange={e => setForm(f => ({ ...f, preferred_roles: e.target.value }))}
            placeholder="Frontend Developer, React Engineer"
            className={inp} />
        </div>

        <div>
          <label className="block text-sm text-gray-400 mb-1">
            Preferred Locations <span className="text-gray-600">(comma-separated)</span>
          </label>
          <input type="text" value={form.preferred_locations}
            onChange={e => setForm(f => ({ ...f, preferred_locations: e.target.value }))}
            placeholder="Remote, Dubai, London"
            className={inp} />
        </div>

        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider pt-1">Salary Filter</h3>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1">Min (USD / year)</label>
            <input type="number" min={0}
              value={form.salary_min ?? ''}
              onChange={e => setForm(f => ({ ...f, salary_min: e.target.value ? parseInt(e.target.value) : null }))}
              placeholder="e.g. 40000"
              className={inp} />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Max (USD / year)</label>
            <input type="number" min={0}
              value={form.salary_max ?? ''}
              onChange={e => setForm(f => ({ ...f, salary_max: e.target.value ? parseInt(e.target.value) : null }))}
              placeholder="e.g. 120000"
              className={inp} />
          </div>
        </div>
        <p className="text-gray-600 text-xs">Jobs with no listed salary are always kept — only out-of-range listings are filtered.</p>

        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider pt-1">Job Type</h3>

        <div className="grid grid-cols-3 gap-2">
          {['full-time', 'contract', 'part-time'].map(jt => (
            <button key={jt} type="button"
              onClick={() => setForm(f => ({ ...f, job_type: jt }))}
              className={`py-2 px-3 rounded-lg text-sm font-medium border transition ${
                form.job_type === jt
                  ? 'bg-blue-600 border-blue-500 text-white'
                  : 'bg-gray-800 border-gray-700 text-gray-400 hover:text-white hover:border-gray-600'
              }`}>
              {jt.charAt(0).toUpperCase() + jt.slice(1)}
            </button>
          ))}
        </div>

        <label className="flex items-center gap-3 cursor-pointer pt-1">
          <div
            onClick={() => setForm(f => ({ ...f, open_to_remote: !f.open_to_remote }))}
            className={`relative w-10 h-5 rounded-full transition-colors ${form.open_to_remote ? 'bg-blue-600' : 'bg-gray-700'}`}>
            <span className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${form.open_to_remote ? 'translate-x-5' : ''}`} />
          </div>
          <span className="text-sm text-gray-300">Open to remote work</span>
        </label>

        {result && (
          <div className={`px-4 py-3 rounded-lg border text-sm ${
            result.ok ? 'bg-emerald-950 border-emerald-800 text-emerald-400' : 'bg-red-950 border-red-800 text-red-400'
          }`}>
            {result.msg}
          </div>
        )}

        <button type="submit" disabled={saving}
          className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-semibold px-6 py-2.5 rounded-xl transition text-sm">
          {saving ? 'Saving…' : 'Save Preferences'}
        </button>
      </form>
    </div>
  )
}
