import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from './api.js'
import { useAuth } from './auth.jsx'

export default function AuthPage() {
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { login } = useAuth()
  const nav = useNavigate()

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const fn = mode === 'login' ? api.login : api.register
      const res = await fn(email, password)
      login(res.user, res.access_token)
      nav('/')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center',
      justifyContent: 'center', background: 'var(--bg)',
      backgroundImage: 'radial-gradient(ellipse 60% 50% at 50% 0%, #1a2a0020 0%, transparent 100%)',
    }}>
      <div style={{ width: 360 }} className="fade-up">
        {/* Logo */}
        <div style={{ textAlign: 'center', marginBottom: 40 }}>
          <div style={{
            fontFamily: 'var(--sans)', fontSize: 28, fontWeight: 800,
            color: 'var(--text)', letterSpacing: '-1px',
          }}>
            SYN<span style={{ color: 'var(--accent)' }}>APSE</span>
          </div>
          <div style={{ color: 'var(--muted)', fontSize: 12, marginTop: 4, fontFamily: 'var(--mono)' }}>
            local-first rag platform
          </div>
        </div>

        <div className="card" style={{ padding: 28 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 20 }}>
            {mode === 'login' ? 'Sign in' : 'Create account'}
          </h2>

          <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <input
              type="email" placeholder="Email" value={email}
              onChange={e => setEmail(e.target.value)} required
            />
            <input
              type="password" placeholder="Password" value={password}
              onChange={e => setPassword(e.target.value)} required
            />
            {error && (
              <div style={{
                color: 'var(--danger)', fontSize: 12,
                padding: '8px 10px', background: '#2a000010',
                borderRadius: 'var(--radius)', border: '1px solid #4a000030',
              }}>
                {error}
              </div>
            )}
            <button type="submit" className="btn btn-primary" disabled={loading} style={{ marginTop: 4 }}>
              {loading ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}
            </button>
          </form>

          <div style={{ marginTop: 16, textAlign: 'center', color: 'var(--muted)', fontSize: 12 }}>
            {mode === 'login' ? "Don't have an account? " : 'Already have an account? '}
            <button
              onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError('') }}
              style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: 12 }}
            >
              {mode === 'login' ? 'Register' : 'Sign in'}
            </button>
          </div>
        </div>

        <div style={{ textAlign: 'center', marginTop: 16, color: 'var(--muted)', fontSize: 11, fontFamily: 'var(--mono)' }}>
          100% local · no data leaves your server
        </div>
      </div>
    </div>
  )
}
