'use client'
import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

export default function PendingRedirect() {
  const router = useRouter()
  useEffect(() => { router.replace('/dashboard/drafts') }, [])
  return null
}
