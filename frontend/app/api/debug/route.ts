import { NextResponse } from 'next/server'
export async function GET() {
  const backend = process.env.BACKEND_URL || 'http://localhost:8000'
  let reachable = false
  try {
    const res = await fetch(`${backend}/health`, { signal: AbortSignal.timeout(5000) })
    reachable = res.ok
  } catch {}
  return NextResponse.json({ backend_url: backend, reachable })
}
