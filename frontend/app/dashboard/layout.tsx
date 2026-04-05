'use client'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'

const sidebarItems = [
  { href: '/dashboard', label: 'Overview', icon: '▦', exact: true },
  { href: '/dashboard/jobs', label: 'Matched Jobs', icon: '🎯' },
  { href: '/dashboard/drafts', label: 'Application Drafts', icon: '✍️' },
  { href: '/dashboard/applied', label: 'Applied', icon: '📤' },
  { href: '/dashboard/guide', label: 'Guide', icon: '📖' },
]

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const router = useRouter()
  const [userName, setUserName] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(false)

  useEffect(() => {
    if (!localStorage.getItem('token')) {
      router.push('/login')
    }
    setUserName(localStorage.getItem('user_name') || 'User')
  }, [])

  const logout = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('api_key')
    localStorage.removeItem('user_name')
    router.push('/')
  }

  const isActive = (item: { href: string; exact?: boolean }) =>
    item.exact ? pathname === item.href : pathname.startsWith(item.href)

  return (
    <div className="min-h-screen flex bg-gray-950">
      {/* Sidebar */}
      <aside className={`fixed inset-y-0 left-0 z-40 w-60 bg-gray-900 border-r border-gray-800 flex flex-col transition-transform duration-200
        ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'} md:relative md:translate-x-0`}>

        {/* Logo */}
        <div className="h-16 flex items-center px-5 border-b border-gray-800 flex-shrink-0">
          <Link href="/" className="flex items-center gap-2 font-bold text-lg text-white">
            <span className="w-7 h-7 bg-blue-600 rounded-lg flex items-center justify-center text-sm font-black">A</span>
            ApplyAI
          </Link>
        </div>

        {/* Nav items */}
        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {sidebarItems.map(item => (
            <Link
              key={item.href}
              href={item.href}
              onClick={() => setSidebarOpen(false)}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition ${
                isActive(item)
                  ? 'bg-blue-600 text-white'
                  : 'text-gray-400 hover:text-white hover:bg-gray-800'
              }`}>
              <span className="text-base leading-none">{item.icon}</span>
              {item.label}
            </Link>
          ))}
        </nav>

        {/* User + logout */}
        <div className="px-3 py-4 border-t border-gray-800 space-y-1 flex-shrink-0">
          <div className="px-3 py-2 text-xs text-gray-600">Signed in as</div>
          <div className="px-3 py-1.5 text-sm text-gray-300 font-medium truncate">{userName}</div>
          <button
            onClick={logout}
            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-gray-500 hover:text-red-400 hover:bg-gray-800 transition">
            <span>↩</span>
            Log Out
          </button>
        </div>
      </aside>

      {/* Mobile overlay */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-30 bg-black/50 md:hidden" onClick={() => setSidebarOpen(false)} />
      )}

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top bar */}
        <header className="h-16 border-b border-gray-800 flex items-center px-6 bg-gray-950 flex-shrink-0">
          <button className="md:hidden text-gray-400 hover:text-white mr-4"
            onClick={() => setSidebarOpen(v => !v)}>
            ☰
          </button>
          <h1 className="text-white font-semibold capitalize">
            {sidebarItems.find(i => isActive(i))?.label ?? 'Dashboard'}
          </h1>
        </header>

        <main className="flex-1 p-6 overflow-y-auto">
          {children}
        </main>
      </div>
    </div>
  )
}
