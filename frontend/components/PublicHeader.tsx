'use client'
import Link from 'next/link'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'

const navLinks = [
  { href: '/#how-it-works', label: 'How it works' },
  { href: '/#features', label: 'Features' },
  { href: '/#benefits', label: 'Benefits' },
  { href: '/guide', label: 'Guide' },
]

export default function PublicHeader() {
  const [loggedIn, setLoggedIn] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  const router = useRouter()

  useEffect(() => {
    setLoggedIn(!!localStorage.getItem('token'))
    const onScroll = () => setScrolled(window.scrollY > 10)
    window.addEventListener('scroll', onScroll)
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <header className={`fixed top-0 inset-x-0 z-50 transition-all duration-200 ${
      scrolled ? 'bg-gray-950/95 backdrop-blur border-b border-gray-800 shadow-lg' : 'bg-transparent'
    }`}>
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2 font-bold text-xl text-white">
          <span className="w-7 h-7 bg-blue-600 rounded-lg flex items-center justify-center text-sm font-black">A</span>
          ApplyAI
        </Link>

        {/* Nav */}
        <nav className="hidden md:flex items-center gap-7">
          {navLinks.map(l => (
            <Link key={l.href} href={l.href}
              className="text-sm text-gray-400 hover:text-white transition">
              {l.label}
            </Link>
          ))}
        </nav>

        {/* Auth buttons */}
        <div className="flex items-center gap-3">
          {loggedIn ? (
            <Link href="/dashboard"
              className="bg-blue-600 hover:bg-blue-500 text-white font-semibold px-5 py-2 rounded-lg transition text-sm">
              Go to Dashboard
            </Link>
          ) : (
            <>
              <Link href="/login"
                className="text-sm text-gray-300 hover:text-white font-medium transition px-4 py-2 rounded-lg hover:bg-gray-800">
                Log In
              </Link>
              <Link href="/signup"
                className="bg-blue-600 hover:bg-blue-500 text-white font-semibold px-5 py-2 rounded-lg transition text-sm">
                Sign Up
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  )
}
