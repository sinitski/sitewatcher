import { useEffect, useState } from 'react'
import { useNavigate, Link, useLocation } from 'react-router-dom'
import { useAuth } from '../store/auth'
import { Eye, EyeOff, Radio } from 'lucide-react'
import api from '../api'

export default function AuthPage({ mode = 'login' }) {
  const { login, register } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [noticeTone, setNoticeTone] = useState('success')
  const [loading, setLoading] = useState(false)
  const [resending, setResending] = useState(false)
  const [resendCooldown, setResendCooldown] = useState(0)

  const isLogin = mode === 'login'

  const validatePassword = (value) => {
    if (value.length < 8) return 'Password must be at least 8 characters'
    if (!/[A-Za-z]/.test(value)) return 'Password must include at least one letter'
    if (!/\d/.test(value)) return 'Password must include at least one digit'
    if (!/[^A-Za-z0-9]/.test(value)) return 'Password must include at least one special character'
    return ''
  }

  useEffect(() => {
    const verified = new URLSearchParams(location.search).get('verified')
    if (verified === 'success') {
      setNotice('Email confirmed. You can sign in now.')
      setNoticeTone('success')
    } else if (verified === 'expired') {
      setNotice('The confirmation link expired. Request a new one below.')
      setNoticeTone('warning')
    } else if (verified === 'invalid') {
      setNotice('The confirmation link is invalid. Request a new one below.')
      setNoticeTone('warning')
    }
  }, [location.search])

  useEffect(() => {
    if (resendCooldown <= 0) return
    const timer = setInterval(() => {
      setResendCooldown((prev) => (prev > 0 ? prev - 1 : 0))
    }, 1000)
    return () => clearInterval(timer)
  }, [resendCooldown])

  const resendConfirmation = async () => {
    if (!email.trim() || resendCooldown > 0) return
    setError('')
    setResending(true)
    try {
      const { data } = await api.post('/auth/verification-email', { email })
      setNotice(data.message || 'A new confirmation link has been sent.')
      setNoticeTone('success')
      setResendCooldown(60)
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not resend confirmation email')
    } finally {
      setResending(false)
    }
  }

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    setNotice('')

    if (!isLogin) {
      const passwordError = validatePassword(password)
      if (passwordError) {
        setError(passwordError)
        return
      }
    }

    setLoading(true)
    try {
      if (isLogin) {
        await login(email, password)
        navigate('/dashboard')
      } else {
        const data = await register(email, password)
        setPassword('')
        setNotice(data.message || 'Check your inbox to confirm your email address.')
        setNoticeTone('success')
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-surface flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="flex items-center justify-center gap-2 mb-8">
          <Radio className="text-brand-500" size={28} />
          <span className="text-xl font-bold tracking-tight">SiteWatcher</span>
        </div>

        <div className="card">
          <h1 className="text-lg font-semibold mb-1">
            {isLogin ? 'Welcome back' : 'Create account'}
          </h1>
          <p className="text-sm text-gray-500 mb-5">
            {isLogin ? 'Sign in to your dashboard' : 'Start monitoring for free'}
          </p>

          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Email</label>
              <input
                className="input"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                required
                autoFocus
              />
              {!isLogin && (
                <p className="text-xs text-gray-500 mt-1">
                  Use a valid email to receive a confirmation link.
                </p>
              )}
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Password</label>
              <div className="relative">
                <input
                  className="input pr-10"
                  type={showPw ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={isLogin ? '••••••••' : 'Min. 8 characters'}
                  required
                />
                <button
                  type="button"
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300"
                  onClick={() => setShowPw(!showPw)}
                >
                  {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
              {!isLogin && (
                <p className="text-xs text-gray-500 mt-1">
                  At least 8 chars, with a letter, a number, and a special symbol.
                </p>
              )}
            </div>

            {notice && (
              <div className={`text-sm rounded-lg px-3 py-2 border ${noticeTone === 'success' ? 'text-emerald-300 bg-emerald-500/10 border-emerald-500/20' : 'text-amber-300 bg-amber-500/10 border-amber-500/20'}`}>
                {notice}
              </div>
            )}

            {error && (
              <div className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
                {error}
              </div>
            )}

            {email.trim() && (notice || (isLogin && error.toLowerCase().includes('confirm your email address'))) && (
              <button
                type="button"
                className="text-xs text-brand-500 hover:text-brand-600 disabled:text-gray-500 disabled:hover:text-gray-500"
                onClick={resendConfirmation}
                disabled={resending || resendCooldown > 0}
              >
                {resending
                  ? 'Sending...'
                  : resendCooldown > 0
                    ? `Resend confirmation email (${resendCooldown}s)`
                    : 'Resend confirmation email'}
              </button>
            )}

            <button className="btn-primary w-full" disabled={loading}>
              {loading ? 'Loading…' : isLogin ? 'Sign In' : 'Create Account'}
            </button>
          </form>
        </div>

        <p className="text-center text-sm text-gray-500 mt-4">
          {isLogin ? "Don't have an account? " : 'Already have an account? '}
          <Link
            to={isLogin ? '/register' : '/login'}
            className="text-brand-500 hover:text-brand-600"
          >
            {isLogin ? 'Sign up' : 'Sign in'}
          </Link>
        </p>

        {!isLogin && (
          <p className="text-center text-xs text-gray-600 mt-3">
            Free tier: 1 site, checks every 60 min
          </p>
        )}
      </div>
    </div>
  )
}
