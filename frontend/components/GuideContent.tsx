export default function GuideContent() {
  const steps = [
    { n: 1, title: 'Create an Account', desc: 'Sign up with your name, email, password, OpenAI API key, and Gmail credentials. Everything sensitive is hashed before storage.' },
    { n: 2, title: 'Run the Pipeline', desc: 'Upload your resume (PDF or DOCX), enter your target location and role preference. The agent handles the rest automatically.' },
    { n: 3, title: 'AI Matches Jobs', desc: 'The agent scrapes live job listings from 3 sources, extracts your skills, and scores each job. Only 40%+ relevant matches are shown.' },
    { n: 4, title: 'Apply to Jobs', desc: 'Click "Apply" on any matched job. The AI generates a personalized cold email for that specific role and queues it for your review.' },
    { n: 5, title: 'You Review & Approve', desc: 'Check the Pending page — each draft shows the subject, body, and recipient. Click Approve to send, or Reject to discard.' },
    { n: 6, title: 'Application Sent', desc: 'Only after your explicit approval does the agent email the recruiter — with your resume attached. Sent emails are logged in Email Sent.' },
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

      {/* OpenAI */}
      <section id="openai" className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-4 scroll-mt-6">
        <h2 className="text-xl font-semibold text-white">OpenAI API Key</h2>
        <p className="text-gray-400 text-sm">The agent uses GPT-4o-mini to write personalized emails. You need your own API key — usage is billed to your OpenAI account (typically under $0.01 per run).</p>
        <ol className="space-y-2 text-sm">
          {[
            <>Go to <span className="text-blue-400">platform.openai.com</span> and log in</>,
            <>In the left sidebar, click <span className="bg-gray-800 px-1.5 py-0.5 rounded font-mono text-xs text-gray-200">API keys</span></>,
            <>Click <span className="text-white font-medium">Create new secret key</span>, name it "ApplyAI"</>,
            <>Copy the key — starts with <span className="bg-gray-800 px-1.5 py-0.5 rounded font-mono text-xs text-green-400">sk-proj-</span> and shown only once</>,
            <>Paste it in the OpenAI API Key field on signup, and enter it again at login</>,
          ].map((step, i) => (
            <li key={i} className="flex gap-3 text-gray-400">
              <span className="text-gray-600 flex-shrink-0">{i + 1}.</span>
              <span>{step}</span>
            </li>
          ))}
        </ol>
      </section>

      {/* Mail */}
      <section id="mail" className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-6 scroll-mt-6">
        <div>
          <h2 className="text-xl font-semibold text-white">Mail Credentials</h2>
          <p className="text-gray-400 text-sm mt-2">The agent uses your Gmail to send email previews to you and application emails to recruiters (only after approval).</p>
        </div>

        <div className="space-y-3">
          <h3 className="text-white font-semibold">What is a Gmail App Password?</h3>
          <p className="text-sm text-gray-400">A 16-character password Google generates for third-party apps. It is <span className="text-white font-medium">not</span> your Gmail login password and can be revoked anytime.</p>
          <div className="bg-yellow-950 border border-yellow-800 rounded-lg px-4 py-3 text-yellow-300 text-sm">
            App Passwords require 2-Step Verification to be enabled on your Google account first.
          </div>
        </div>

        <div className="space-y-3">
          <h3 className="text-white font-semibold">Generate a Gmail App Password</h3>
          <ol className="space-y-3 text-sm">
            {[
              <>Go to <span className="text-blue-400">myaccount.google.com</span> → Security</>,
              <>Enable <span className="text-white font-medium">2-Step Verification</span> if not already on</>,
              <>Search for <span className="text-white font-medium">App passwords</span> in the search bar</>,
              <>Select app: <span className="bg-gray-800 px-1.5 py-0.5 rounded font-mono text-xs text-gray-200">Mail</span>, device: <span className="bg-gray-800 px-1.5 py-0.5 rounded font-mono text-xs text-gray-200">Other</span>, name it "ApplyAI"</>,
              <>Click <span className="text-white font-medium">Generate</span> — copy the 16-char password (e.g. <span className="bg-gray-800 px-1.5 py-0.5 rounded font-mono text-xs text-green-400">abcdabcdabcdabcd</span>)</>,
              <>Paste it (without spaces) into the Gmail App Password field on signup</>,
            ].map((step, i) => (
              <li key={i} className="flex gap-3 text-gray-400">
                <span className="text-gray-600 flex-shrink-0 w-4">{i + 1}.</span>
                <span>{step}</span>
              </li>
            ))}
          </ol>
        </div>

        <div className="divide-y divide-gray-800 rounded-xl overflow-hidden border border-gray-800 text-sm">
          {[
            { field: 'Gmail Address', example: 'you@gmail.com', desc: 'The Gmail account used to send and receive emails' },
            { field: 'Gmail App Password', example: 'abcdabcdabcdabcd', desc: '16-character App Password — not your Gmail login password' },
            { field: 'SMTP Host', example: 'smtp.gmail.com', desc: "Gmail's outgoing mail server — leave as default" },
            { field: 'SMTP Port', example: '587', desc: 'Port for STARTTLS encryption — 587 is correct for Gmail' },
          ].map(row => (
            <div key={row.field} className="bg-gray-950 px-5 py-3 grid grid-cols-3 gap-4">
              <div>
                <div className="text-white font-medium">{row.field}</div>
                <div className="text-gray-500 font-mono text-xs mt-0.5">{row.example}</div>
              </div>
              <div className="col-span-2 text-gray-400 text-xs flex items-center">{row.desc}</div>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
