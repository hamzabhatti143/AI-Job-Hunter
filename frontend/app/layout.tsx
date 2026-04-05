import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: {
    default: 'ApplyAI — AI Job Matching & Automated Applications',
    template: '%s | ApplyAI',
  },
  description: 'Upload your resume and let ApplyAI match you with relevant jobs, write personalized cold emails, and send applications — with your approval every step of the way.',
  keywords: ['job matching', 'AI job search', 'automated job applications', 'resume matching', 'cold email', 'job agent', 'career AI'],
  authors: [{ name: 'ApplyAI' }],
  openGraph: {
    title: 'ApplyAI — AI Job Matching & Automated Applications',
    description: 'Upload your resume. Get matched jobs. Send applications automatically with AI.',
    type: 'website',
  },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-gray-950 text-gray-100 min-h-screen">
        {children}
      </body>
    </html>
  )
}
