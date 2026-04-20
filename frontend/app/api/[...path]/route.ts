import { NextRequest, NextResponse } from 'next/server'

export const maxDuration = 300 // 5 minutes — pipeline can take a while

const BACKEND = process.env.BACKEND_URL || 'https://hamzabhatti-job-hunter.hf.space'

async function handler(
  req: NextRequest,
  { params }: { params: { path: string[] } }
) {
  const path = params.path.join('/')
  const url = `${BACKEND}/${path}${req.nextUrl.search}`

  // Forward headers — critically, Content-Type for multipart must include the boundary
  const forwardHeaders: Record<string, string> = {}
  const contentType = req.headers.get('content-type')
  if (contentType) forwardHeaders['content-type'] = contentType
  const auth = req.headers.get('authorization')
  if (auth) forwardHeaders['authorization'] = auth

  // Use arrayBuffer to preserve binary data (required for multipart/form-data)
  const body =
    req.method !== 'GET' && req.method !== 'HEAD'
      ? await req.arrayBuffer()
      : undefined

  try {
    const res = await fetch(url, {
      method: req.method,
      headers: forwardHeaders,
      body: body !== undefined ? Buffer.from(body) : undefined,
    })

    const resBody = await res.arrayBuffer()
    const resContentType = res.headers.get('content-type') || 'application/json'

    return new NextResponse(resBody, {
      status: res.status,
      headers: { 'content-type': resContentType },
    })
  } catch {
    return NextResponse.json({ detail: 'Backend unreachable' }, { status: 502 })
  }
}

export const GET    = handler
export const POST   = handler
export const PUT    = handler
export const PATCH  = handler
export const DELETE = handler
