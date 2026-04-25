export default function GuideContent() {
  const steps = [
    { n: 1, title: 'Create an Account', desc: 'Sign up with your name, email, and password. Your email is used as your identity — recruiters who reply will reach this inbox.' },
    { n: 2, title: 'Connect Gmail', desc: 'Go to Settings and click Connect Gmail. Authorize ApplyAI once — no password stored. This is required to send application emails.' },
    { n: 3, title: 'Run the Pipeline', desc: 'Upload your resume (PDF or DOCX), enter your target location and role preference. The agent handles the rest automatically.' },
    { n: 4, title: 'AI Matches Jobs', desc: 'The agent scrapes live job listings from 3 sources, extracts your skills, and scores each job. Only 40%+ relevant matches are shown.' },
    { n: 5, title: 'Apply to Jobs', desc: 'Click "Apply" on any matched job. The AI generates a personalized cold email for that specific role and queues it for your review.' },
    { n: 6, title: 'You Review & Approve', desc: 'Check the Pending page — each draft shows the subject, body, and recipient. Click Approve to send, or Reject to discard.' },
    { n: 7, title: 'Application Sent & Tracked', desc: 'After approval the email is sent from your own Gmail with your resume attached. When a recruiter replies, it shows up automatically in Sent Emails.' },
  ]

  return (
    <div className="space-y-12 py-2">
      <div>
        <h1 className="text-3xl font-bold text-white">How It Works</h1>
        <p className="text-gray-400 mt-2">A step-by-step guide to the ApplyAI pipeline</p>
      </div>

      {/* Pipeline steps */}
      <section className="space-y-3">
        {steps.map(s => (
          <div key={s.n} className="bg-gray-900 border border-gray-800 rounded-xl p-5 flex gap-5 items-start">
            <div className="w-9 h-9 bg-blue-600 rounded-full flex items-center justify-center text-white font-bold text-sm flex-shrink-0 mt-0.5">
              {s.n}
            </div>
            <div>
              <h3 className="text-white font-semibold">{s.title}</h3>
              <p className="text-gray-400 text-sm mt-1">{s.desc}</p>
            </div>
          </div>
        ))}
      </section>

      {/* Gmail Setup */}
      <section id="gmail" className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-6 scroll-mt-6">
        <div>
          <h2 className="text-xl font-semibold text-white">Gmail API Setup</h2>
          <p className="text-gray-400 text-sm mt-2">
            ApplyAI sends application emails using your own Gmail account via Google's secure OAuth.
            No password is ever stored — only a token that you can revoke anytime.
            This is a one-time setup done once by the person deploying the app on Hugging Face.
          </p>
        </div>

        {/* Summary table */}
        <div className="divide-y divide-gray-800 rounded-xl overflow-hidden border border-gray-800 text-sm">
          {[
            { label: 'FROM address',    value: "User's own Gmail",           desc: 'Each user connects their Gmail — emails come from their personal address' },
            { label: 'Reply tracking',  value: 'Automatic via Gmail threads', desc: 'Recruiter replies are detected when the user opens the Sent Emails page' },
            { label: 'Cost',            value: 'Free',                        desc: 'Gmail API is completely free with a standard Google account' },
            { label: 'Setup location',  value: 'Google Cloud Console',        desc: 'One-time project + credentials setup, then add 3 secrets to HF Spaces' },
          ].map(row => (
            <div key={row.label} className="bg-gray-950 px-5 py-3 grid grid-cols-3 gap-4">
              <div>
                <div className="text-white font-medium">{row.label}</div>
                <div className="text-gray-500 font-mono text-xs mt-0.5">{row.value}</div>
              </div>
              <div className="col-span-2 text-gray-400 text-xs flex items-center">{row.desc}</div>
            </div>
          ))}
        </div>

        {/* Step 1 */}
        <div className="space-y-3">
          <h3 className="text-white font-semibold">Step 1 — Create a Google Cloud project</h3>
          <ol className="space-y-2 text-sm">
            {[
              <>Go to <span className="text-blue-400">console.cloud.google.com</span> and sign in with your Google account</>,
              <>Click the project selector at the top → <span className="text-white font-medium">New Project</span></>,
              <>Name it <span className="bg-gray-800 px-1.5 py-0.5 rounded font-mono text-xs text-gray-200">ApplyAI</span> → click <span className="text-white font-medium">Create</span></>,
              <>Wait a few seconds, then select the new project from the dropdown at the top</>,
            ].map((s, i) => (
              <li key={i} className="flex gap-3 text-gray-400">
                <span className="text-gray-600 flex-shrink-0 w-4">{i + 1}.</span><span>{s}</span>
              </li>
            ))}
          </ol>
        </div>

        {/* Step 2 */}
        <div className="space-y-3">
          <h3 className="text-white font-semibold">Step 2 — Enable the Gmail API</h3>
          <ol className="space-y-2 text-sm">
            {[
              <>In the left sidebar go to <span className="bg-gray-800 px-1.5 py-0.5 rounded font-mono text-xs text-gray-200">APIs & Services</span> → <span className="text-white font-medium">Library</span></>,
              <>Search for <span className="text-white font-medium">Gmail API</span> and click on it</>,
              <>Click <span className="text-white font-medium">Enable</span> — the page refreshes to show the API is active</>,
            ].map((s, i) => (
              <li key={i} className="flex gap-3 text-gray-400">
                <span className="text-gray-600 flex-shrink-0 w-4">{i + 1}.</span><span>{s}</span>
              </li>
            ))}
          </ol>
        </div>

        {/* Step 3 */}
        <div className="space-y-3">
          <h3 className="text-white font-semibold">Step 3 — Configure the OAuth consent screen</h3>
          <p className="text-sm text-gray-400">This is the screen users see when they click "Connect Gmail". You only configure it once.</p>
          <ol className="space-y-2 text-sm">
            {[
              <>Go to <span className="bg-gray-800 px-1.5 py-0.5 rounded font-mono text-xs text-gray-200">APIs & Services</span> → <span className="text-white font-medium">OAuth consent screen</span></>,
              <>User type: select <span className="text-white font-medium">External</span> → click <span className="text-white font-medium">Create</span></>,
              <>Fill in App name: <span className="bg-gray-800 px-1.5 py-0.5 rounded font-mono text-xs text-gray-200">ApplyAI</span>, User support email: your email, Developer contact: your email → click <span className="text-white font-medium">Save and Continue</span></>,
              <>On the Scopes page click <span className="text-white font-medium">Add or Remove Scopes</span> — search and add these two scopes:
                <div className="mt-1 space-y-1">
                  <div className="bg-gray-800 px-2 py-1 rounded font-mono text-xs text-green-400">https://www.googleapis.com/auth/gmail.send</div>
                  <div className="bg-gray-800 px-2 py-1 rounded font-mono text-xs text-green-400">https://www.googleapis.com/auth/gmail.readonly</div>
                </div>
              </>,
              <>Click <span className="text-white font-medium">Update</span> then <span className="text-white font-medium">Save and Continue</span></>,
              <>On the Test users page click <span className="text-white font-medium">Add Users</span> and add your own Gmail address (and any other emails that will use the app) → <span className="text-white font-medium">Save and Continue</span></>,
            ].map((s, i) => (
              <li key={i} className="flex gap-3 text-gray-400">
                <span className="text-gray-600 flex-shrink-0 w-4">{i + 1}.</span><span>{s}</span>
              </li>
            ))}
          </ol>
          <div className="bg-yellow-950 border border-yellow-800 rounded-lg px-4 py-3 text-yellow-300 text-sm">
            <strong>Important:</strong> While your app is in "Testing" mode, only the Gmail addresses you added as Test Users can connect. To allow any Google account, you need to publish the app — go to OAuth consent screen → <span className="font-medium">Publish App</span>. For personal use, staying in Testing mode is fine.
          </div>
        </div>

        {/* Step 4 */}
        <div className="space-y-3">
          <h3 className="text-white font-semibold">Step 4 — Create OAuth credentials</h3>
          <ol className="space-y-2 text-sm">
            {[
              <>Go to <span className="bg-gray-800 px-1.5 py-0.5 rounded font-mono text-xs text-gray-200">APIs & Services</span> → <span className="text-white font-medium">Credentials</span> → <span className="text-white font-medium">Create Credentials</span> → <span className="text-white font-medium">OAuth client ID</span></>,
              <>Application type: select <span className="text-white font-medium">Web application</span></>,
              <>Name it <span className="bg-gray-800 px-1.5 py-0.5 rounded font-mono text-xs text-gray-200">ApplyAI Backend</span></>,
              <>Under <span className="text-white font-medium">Authorized redirect URIs</span> click <span className="text-white font-medium">Add URI</span> and enter your backend callback URL:
                <div className="mt-1 bg-gray-800 px-2 py-1 rounded font-mono text-xs text-green-400">
                  https://your-backend-space.hf.space/auth/gmail/callback
                </div>
                <p className="text-gray-500 text-xs mt-1">Replace <span className="text-gray-300">your-backend-space</span> with your actual HF Space name. For local dev also add <span className="font-mono text-gray-300">http://localhost:8000/auth/gmail/callback</span></p>
              </>,
              <>Click <span className="text-white font-medium">Create</span> — a dialog shows your <span className="text-white font-medium">Client ID</span> and <span className="text-white font-medium">Client Secret</span>. Copy both — keep them safe</>,
            ].map((s, i) => (
              <li key={i} className="flex gap-3 text-gray-400">
                <span className="text-gray-600 flex-shrink-0 w-4">{i + 1}.</span><span>{s}</span>
              </li>
            ))}
          </ol>
        </div>

        {/* Step 5 */}
        <div className="space-y-3">
          <h3 className="text-white font-semibold">Step 5 — Add secrets to Hugging Face Spaces</h3>
          <ol className="space-y-2 text-sm">
            {[
              <>Go to your backend HF Space → <span className="text-white font-medium">Settings</span> tab → <span className="text-white font-medium">Variables and secrets</span></>,
              <>Click <span className="text-white font-medium">New secret</span> and add these three secrets:</>,
            ].map((s, i) => (
              <li key={i} className="flex gap-3 text-gray-400">
                <span className="text-gray-600 flex-shrink-0 w-4">{i + 1}.</span><span>{s}</span>
              </li>
            ))}
          </ol>
          <div className="divide-y divide-gray-800 rounded-xl overflow-hidden border border-gray-800 text-sm mt-2">
            {[
              { name: 'GOOGLE_CLIENT_ID',     value: '1234567890-abc...apps.googleusercontent.com', desc: 'Client ID from the OAuth credentials dialog' },
              { name: 'GOOGLE_CLIENT_SECRET', value: 'GOCSPX-xxxxx',                                desc: 'Client Secret from the OAuth credentials dialog' },
              { name: 'GOOGLE_REDIRECT_URI',  value: 'https://your-backend.hf.space/auth/gmail/callback', desc: 'Must exactly match what you entered in Google Cloud Console' },
            ].map(row => (
              <div key={row.name} className="bg-gray-950 px-5 py-3 grid grid-cols-3 gap-4">
                <div>
                  <div className="text-green-400 font-mono text-xs font-medium">{row.name}</div>
                  <div className="text-gray-600 font-mono text-xs mt-0.5 truncate">{row.value}</div>
                </div>
                <div className="col-span-2 text-gray-400 text-xs flex items-center">{row.desc}</div>
              </div>
            ))}
          </div>
          <p className="text-xs text-gray-500">Click <span className="text-gray-300 font-medium">Save</span> after adding each secret — the Space restarts automatically.</p>
        </div>

        {/* Step 6 */}
        <div className="space-y-3">
          <h3 className="text-white font-semibold">Step 6 — Connect Gmail in Settings</h3>
          <ol className="space-y-2 text-sm">
            {[
              <>Go to <span className="text-white font-medium">Settings</span> in the dashboard sidebar</>,
              <>Under <span className="text-white font-medium">Gmail — Email Sending</span> click <span className="bg-blue-900 text-blue-200 px-2 py-0.5 rounded text-xs font-medium">Connect Gmail</span></>,
              <>You are redirected to Google's sign-in page — select the Gmail account you want to send from</>,
              <>Google asks for permission to send emails and read Gmail — click <span className="text-white font-medium">Allow</span></>,
              <>You are redirected back to Settings with a confirmation message — the status badge turns green</>,
            ].map((s, i) => (
              <li key={i} className="flex gap-3 text-gray-400">
                <span className="text-gray-600 flex-shrink-0 w-4">{i + 1}.</span><span>{s}</span>
              </li>
            ))}
          </ol>
          <div className="bg-blue-950 border border-blue-800 rounded-lg px-4 py-3 text-blue-300 text-xs space-y-1">
            <p className="font-medium text-blue-200">Each user does Step 6 themselves — it takes 30 seconds</p>
            <p>Steps 1–5 are done once by the app admin. Every user who signs up just needs to click Connect Gmail in their own Settings page. They authorize with their own Gmail account, so emails come from their own address.</p>
          </div>
        </div>

        {/* Step 7 — Reply tracking */}
        <div className="space-y-3">
          <h3 className="text-white font-semibold">Step 7 — Reply tracking (automatic)</h3>
          <p className="text-sm text-gray-400">No setup needed. This works automatically once Gmail is connected.</p>
          <ol className="space-y-2 text-sm">
            {[
              <>When you approve and send an email, ApplyAI saves the Gmail thread ID in the database</>,
              <>Every time you open the <span className="text-white font-medium">Sent Emails</span> page, the app quietly checks each thread for new replies</>,
              <>If a recruiter has replied, a green <span className="bg-emerald-900 text-emerald-300 text-xs px-1.5 py-0.5 rounded font-medium">Replied</span> badge appears on that card</>,
              <>Click the card to expand it and click <span className="text-white font-medium">View recruiter reply</span> to read their response</>,
            ].map((s, i) => (
              <li key={i} className="flex gap-3 text-gray-400">
                <span className="text-gray-600 flex-shrink-0 w-4">{i + 1}.</span><span>{s}</span>
              </li>
            ))}
          </ol>
        </div>
      </section>
    </div>
  )
}
