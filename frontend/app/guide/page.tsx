import type { Metadata } from 'next'
import PublicHeader from '@/components/PublicHeader'
import PublicFooter from '@/components/PublicFooter'
import GuideContent from '@/components/GuideContent'

export const metadata: Metadata = {
  title: 'Guide — How ApplyAI Works',
  description: 'Step-by-step guide to using ApplyAI: uploading your resume, running the pipeline, reviewing emails, and sending applications to recruiters.',
}

export default function GuidePage() {
  return (
    <>
      <PublicHeader />
      <main className="max-w-3xl mx-auto px-6 pt-28 pb-20">
        <GuideContent />
      </main>
      <PublicFooter />
    </>
  )
}
