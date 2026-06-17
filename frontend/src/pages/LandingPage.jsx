import { Link } from 'react-router-dom'
import { Radio, Zap, Bell, Clock, Shield, TrendingUp, ChevronRight, Check, Bot } from 'lucide-react'

const FEATURES = [
  {
    icon: Bell,
    title: 'Instant Telegram alerts',
    desc: 'Get notified the moment your site goes down — before your users notice.',
  },
  {
    icon: Clock,
    title: 'Checks every minute',
    desc: 'Pro users get 60× more coverage. Free tier checks hourly to get you started.',
  },
  {
    icon: TrendingUp,
    title: 'Response time tracking',
    desc: 'Slow sites lose visitors. We catch sluggishness before it becomes an outage.',
  },
  {
    icon: Shield,
    title: 'Content change detection',
    desc: 'Know instantly when your homepage, landing page, or pricing changes unexpectedly.',
  },
  {
    icon: Bot,
    title: 'AI-powered insights',
    desc: 'When something breaks, Claude analyzes the pattern and explains it in plain language.',
  },
  {
    icon: Zap,
    title: 'Weekly AI summaries',
    desc: 'Every Monday, get a digest: uptime %, incident trends, and what to watch.',
  },
]

const TESTIMONIALS = [
  {
    quote: 'Caught a 3am outage and fixed it before our EU team even woke up.',
    name: 'Alex K.',
    role: 'Backend engineer',
  },
  {
    quote: 'The AI told me my site was falling over every night at 2am. Turned out to be a cron job.',
    name: 'Maria S.',
    role: 'Solo founder',
  },
  {
    quote: 'Weekly summaries in Telegram are now part of my Monday morning routine.',
    name: 'Denis P.',
    role: 'DevOps lead',
  },
]

const FREE_FEATURES = ['1 site', 'Hourly checks', 'Uptime + response time', 'Telegram alerts', 'Email alerts: 1 per day']
const PRO_FEATURES = [
  'Up to 50 sites',
  '1-minute checks',
  'Content change detection',
  'AI downtime analysis',
  'AI root-cause hints in alerts',
  'Email alerts: unlimited',
  'Weekly AI summaries',
  'Full check history',
]

function NavBar() {
  return (
    <nav className="fixed top-0 left-0 right-0 z-50 border-b border-white/5 bg-surface/80 backdrop-blur-md">
      <div className="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Radio className="text-brand-500" size={20} />
          <span className="font-bold tracking-tight">SiteWatcher</span>
        </div>
        <div className="flex items-center gap-3">
          <Link to="/login" className="text-sm text-gray-400 hover:text-gray-200 transition-colors px-3 py-1.5">
            Sign in
          </Link>
          <Link
            to="/register"
            className="btn-primary text-sm"
          >
            Start free
          </Link>
        </div>
      </div>
    </nav>
  )
}

function Hero() {
  return (
    <section className="pt-32 pb-20 px-4 text-center relative overflow-hidden">
      {/* Background glow */}
      <div
        className="absolute top-0 left-1/2 -translate-x-1/2 w-[600px] h-[400px] rounded-full pointer-events-none"
        style={{
          background: 'radial-gradient(ellipse at center, rgba(59,91,219,0.15) 0%, transparent 70%)',
        }}
      />

      <div className="relative max-w-3xl mx-auto">
        <div className="inline-flex items-center gap-2 text-xs bg-brand-500/15 text-brand-500 border border-brand-500/20 rounded-full px-3 py-1 mb-6">
          <Bot size={12} />
          Now with AI-powered downtime analysis
        </div>

        <h1 className="text-5xl md:text-6xl font-bold tracking-tight mb-5 leading-tight">
          Know when your site{' '}
          <span className="text-brand-500">goes down</span>
          <br />
          before users do.
        </h1>

        <p className="text-lg text-gray-400 mb-8 max-w-xl mx-auto leading-relaxed">
          Telegram-native monitoring for teams that live in chat.
          Catch outages fast, then get AI root-cause hints in plain language.
        </p>

        <div className="flex items-center justify-center gap-3 flex-wrap">
          <Link
            to="/register"
            className="btn-primary flex items-center gap-2 text-base px-6 py-2.5"
          >
            Start monitoring for free
            <ChevronRight size={16} />
          </Link>
          <a
            href="#how-it-works"
            className="btn-ghost text-sm text-gray-400"
          >
            See how it works
          </a>
        </div>

        <p className="text-xs text-gray-600 mt-4">Free forever • No credit card • Email alerts: Free 1/day, Pro unlimited</p>
      </div>
    </section>
  )
}

function MockAlert() {
  return (
    <section className="px-4 pb-20">
      <div className="max-w-sm mx-auto">
        <p className="text-center text-xs text-gray-600 mb-4 uppercase tracking-wider">Example alert</p>
        {/* Telegram-style mock */}
        <div className="bg-[#17212b] rounded-2xl p-4 shadow-2xl border border-white/5">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-8 h-8 rounded-full bg-brand-500 flex items-center justify-center text-xs font-bold">SW</div>
            <div>
              <p className="text-sm font-semibold text-white">SiteWatcher Bot</p>
              <p className="text-xs text-gray-500">just now</p>
            </div>
          </div>
          <div className="space-y-3 text-sm text-gray-200 leading-relaxed">
            <p>🔴 <strong>Site Down</strong>: My Store<br />
            🌐 <code className="text-xs text-gray-400">https://mystore.com</code><br />
            ❌ Error: Connection timed out</p>
            <div className="border-t border-white/5 pt-3 text-gray-400 text-xs italic">
              🤖 This is the 4th timeout this week, always between 2–4 AM UTC. Likely scheduled maintenance or a nightly cron job overloading the DB. Consider adding a health check endpoint.
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

function HowItWorks() {
  const steps = [
    { n: '1', title: 'Add your site', desc: 'Paste a URL. Name it. Set your check interval.' },
    { n: '2', title: 'Connect Telegram', desc: 'One click in Settings links your account to our bot.' },
    { n: '3', title: 'We watch 24/7', desc: 'HTTP checks run on schedule. AI monitors the patterns.' },
    { n: '4', title: 'Get instant alerts', desc: 'Down, slow, or changed — you\'re the first to know.' },
  ]
  return (
    <section id="how-it-works" className="py-20 px-4 border-t border-border">
      <div className="max-w-4xl mx-auto">
        <h2 className="text-2xl font-bold text-center mb-12">Up and running in 2 minutes</h2>
        <div className="grid sm:grid-cols-2 md:grid-cols-4 gap-6">
          {steps.map((s) => (
            <div key={s.n} className="text-center">
              <div className="w-10 h-10 rounded-full bg-brand-500/15 border border-brand-500/30 text-brand-500 font-bold text-lg flex items-center justify-center mx-auto mb-3">
                {s.n}
              </div>
              <h3 className="font-semibold mb-1">{s.title}</h3>
              <p className="text-sm text-gray-500">{s.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function Features() {
  return (
    <section className="py-20 px-4 border-t border-border">
      <div className="max-w-4xl mx-auto">
        <h2 className="text-2xl font-bold text-center mb-3">Everything you need to sleep soundly</h2>
        <p className="text-gray-500 text-center mb-12 text-sm">No dashboards to check. Just alerts when something needs attention.</p>
        <div className="grid sm:grid-cols-2 md:grid-cols-3 gap-5">
          {FEATURES.map((f) => (
            <div key={f.title} className="card hover:border-brand-500/30 transition-colors">
              <f.icon size={20} className="text-brand-500 mb-3" />
              <h3 className="font-semibold mb-1">{f.title}</h3>
              <p className="text-sm text-gray-500">{f.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function Testimonials() {
  return (
    <section className="py-20 px-4 border-t border-border">
      <div className="max-w-4xl mx-auto">
        <h2 className="text-2xl font-bold text-center mb-12">What users say</h2>
        <div className="grid sm:grid-cols-3 gap-5">
          {TESTIMONIALS.map((t) => (
            <div key={t.name} className="card">
              <p className="text-gray-300 text-sm mb-4 leading-relaxed">"{t.quote}"</p>
              <div>
                <p className="text-sm font-semibold">{t.name}</p>
                <p className="text-xs text-gray-500">{t.role}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function Pricing() {
  return (
    <section id="pricing" className="py-20 px-4 border-t border-border">
      <div className="max-w-3xl mx-auto">
        <h2 className="text-2xl font-bold text-center mb-3">Simple pricing</h2>
        <p className="text-gray-500 text-center mb-12 text-sm">Start free. Upgrade when you're ready.</p>
        <p className="text-xs text-amber-400 text-center mb-8">Email alerts policy: Free plan includes 1 alert per 24h, Pro is unlimited.</p>
        <div className="grid sm:grid-cols-2 gap-5">
          {/* Free */}
          <div className="card">
            <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Free</p>
            <p className="text-3xl font-bold mb-1">$0</p>
            <p className="text-sm text-gray-500 mb-6">Forever</p>
            <ul className="space-y-2 mb-8">
              {FREE_FEATURES.map((f) => (
                <li key={f} className="flex items-center gap-2 text-sm text-gray-400">
                  <Check size={14} className="text-gray-600 shrink-0" /> {f}
                </li>
              ))}
            </ul>
            <Link to="/register" className="btn-ghost w-full text-center block text-sm border border-border">
              Get started
            </Link>
          </div>
          {/* Pro */}
          <div className="card border-brand-500/40 bg-brand-500/5 relative">
            <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-brand-500 text-white text-xs font-semibold px-3 py-0.5 rounded-full">
              PRO
            </div>
            <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Pro</p>
            <p className="text-3xl font-bold mb-1">~$10</p>
            <p className="text-sm text-gray-500 mb-6">One-time payment · 500 ⭐ Telegram Stars</p>
            <ul className="space-y-2 mb-8">
              {PRO_FEATURES.map((f) => (
                <li key={f} className="flex items-center gap-2 text-sm">
                  <Check size={14} className="text-brand-500 shrink-0" /> {f}
                </li>
              ))}
            </ul>
            <Link to="/register" className="btn-primary w-full text-center block text-sm">
              Start free → Upgrade
            </Link>
          </div>
        </div>
      </div>
    </section>
  )
}

function Footer() {
  return (
    <footer className="border-t border-border py-10 px-4">
      <div className="max-w-4xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4 text-sm text-gray-600">
        <div className="flex items-center gap-2">
          <Radio size={16} className="text-brand-500" />
          <span className="font-semibold text-gray-400">SiteWatcher</span>
          <span>— uptime monitoring with AI insights</span>
        </div>
        <div className="flex items-center gap-4">
          <Link to="/login" className="hover:text-gray-400 transition-colors">Sign in</Link>
          <Link to="/register" className="hover:text-gray-400 transition-colors">Sign up</Link>
        </div>
      </div>
    </footer>
  )
}

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-surface">
      <NavBar />
      <Hero />
      <MockAlert />
      <HowItWorks />
      <Features />
      <Testimonials />
      <Pricing />
      <Footer />
    </div>
  )
}
