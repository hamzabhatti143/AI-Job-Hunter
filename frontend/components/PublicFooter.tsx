import Link from 'next/link'

export default function PublicFooter() {
  return (
    <footer className="border-t border-gray-800 bg-gray-950">
      <div className="max-w-6xl mx-auto px-6 py-12">
        <div className="grid md:grid-cols-4 gap-10">
          {/* Brand */}
          <div className="md:col-span-2 space-y-3">
            <div className="flex items-center gap-2 font-bold text-xl text-white">
              <span className="w-7 h-7 bg-blue-600 rounded-lg flex items-center justify-center text-sm font-black">A</span>
              ApplyAI
            </div>
            <p className="text-gray-500 text-sm leading-relaxed max-w-xs">
              AI-powered job matching and automated application emails. Upload your resume,
              set preferences, and let the agent do the work — with your approval every step.
            </p>
          </div>

          {/* Product */}
          <div className="space-y-3">
            <h4 className="text-white font-semibold text-sm">Product</h4>
            <ul className="space-y-2">
              {[
                { href: '/#how-it-works', label: 'How it works' },
                { href: '/#features', label: 'Features' },
                { href: '/#benefits', label: 'Benefits' },
                { href: '/guide', label: 'Guide' },
              ].map(l => (
                <li key={l.href}>
                  <Link href={l.href} className="text-gray-500 hover:text-gray-300 text-sm transition">{l.label}</Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Account */}
          <div className="space-y-3">
            <h4 className="text-white font-semibold text-sm">Account</h4>
            <ul className="space-y-2">
              {[
                { href: '/signup', label: 'Sign Up' },
                { href: '/login', label: 'Log In' },
                { href: '/dashboard', label: 'Dashboard' },
                { href: '/guide#mail', label: 'Mail Setup' },
              ].map(l => (
                <li key={l.href}>
                  <Link href={l.href} className="text-gray-500 hover:text-gray-300 text-sm transition">{l.label}</Link>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="mt-12 pt-6 border-t border-gray-800 flex flex-col md:flex-row items-center justify-between gap-4">
          <p className="text-gray-600 text-sm">© {new Date().getFullYear()} ApplyAI. All rights reserved.</p>
          <p className="text-gray-700 text-xs">
            Uses your own OpenAI API key · Emails sent only with your explicit approval
          </p>
        </div>
      </div>
    </footer>
  )
}
