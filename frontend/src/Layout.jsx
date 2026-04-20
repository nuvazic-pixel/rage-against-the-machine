import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from './auth.jsx'

const NAV = [
  { to: '/',           label: 'Chat',        icon: '◈' },
  { to: '/collections',label: 'Collections', icon: '⬡' },
  { to: '/documents',  label: 'Documents',   icon: '⬚' },
  { to: '/status',     label: 'Status',      icon: '◎' },
]

export default function Layout({ children }) {
  const { user, logout } = useAuth()
  const nav = useNavigate()

  const handleLogout = () => { logout(); nav('/login') }

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      {/* Sidebar */}
      <aside style={{
        width: 200, flexShrink: 0,
        background: 'var(--surface)',
        borderRight: '1px solid var(--border)',
        display: 'flex', flexDirection: 'column',
        padding: '20px 0',
      }}>
        {/* Logo */}
        <div style={{ padding: '0 16px 24px', borderBottom: '1px solid var(--border)', marginBottom: 12 }}>
          <div style={{ fontFamily: 'var(--sans)', fontSize: 18, fontWeight: 800, letterSpacing: '-0.5px' }}>
            SYN<span style={{ color: 'var(--accent)' }}>APSE</span>
          </div>
          <div style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--muted)', marginTop: 2 }}>
            rag platform
          </div>
        </div>

        {/* Nav */}
        <nav style={{ flex: 1, padding: '0 8px' }}>
          {NAV.map(({ to, label, icon }) => (
            <NavLink key={to} to={to} end={to === '/'} style={({ isActive }) => ({
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '8px 10px', borderRadius: 'var(--radius)',
              marginBottom: 2, textDecoration: 'none',
              fontSize: 13, fontWeight: 600,
              color: isActive ? 'var(--accent)' : 'var(--muted)',
              background: isActive ? '#1a2a0020' : 'transparent',
              transition: 'all 0.1s',
            })}>
              <span style={{ fontFamily: 'var(--mono)', fontSize: 14 }}>{icon}</span>
              {label}
            </NavLink>
          ))}
        </nav>

        {/* User */}
        <div style={{
          padding: '12px 16px', borderTop: '1px solid var(--border)',
          display: 'flex', flexDirection: 'column', gap: 6,
        }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', fontFamily: 'var(--mono)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {user?.email}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span className="tag tag-green">{user?.plan}</span>
            <button
              onClick={handleLogout}
              style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: 11 }}
            >
              logout
            </button>
          </div>
        </div>
      </aside>

      {/* Main */}
      <main style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        {children}
      </main>
    </div>
  )
}
