import { useState, useEffect } from 'react'
import { api } from './api.js'

export default function StatusPage() {
  const [status, setStatus] = useState(null)
  const [me, setMe] = useState(null)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    try {
      const [s, m] = await Promise.all([api.status(), api.me()])
      setStatus(s); setMe(m)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])
  useEffect(() => {
    const t = setInterval(load, 5000)
    return () => clearInterval(t)
  }, [])

  if (loading) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--muted)' }}>
      Loading…
    </div>
  )

  return (
    <div style={{ padding: '28px 32px', height: '100%', overflowY: 'auto' }}>
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: 20, fontWeight: 800, letterSpacing: '-0.5px' }}>System Status</h1>
        <div style={{ color: 'var(--muted)', fontSize: 12, marginTop: 2 }}>
          Live cluster health · refreshes every 5s
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 14, marginBottom: 28 }}>
        <StatCard label="Database" value={status?.database} isStatus />
        <StatCard label="Redis" value={status?.redis} isStatus />
        <StatCard label="Queries today" value={me?.usage?.queries_today ?? '—'} />
        <StatCard label="Documents indexed" value={me?.usage?.documents ?? '—'} />
      </div>

      {/* LLM Nodes */}
      <div style={{ marginBottom: 20 }}>
        <h2 style={{ fontSize: 14, fontWeight: 700, marginBottom: 14, color: 'var(--muted)', letterSpacing: '0.05em', textTransform: 'uppercase', fontFamily: 'var(--mono)' }}>
          LLM Nodes
        </h2>

        {!status?.llm_nodes?.length ? (
          <div style={{ color: 'var(--muted)', fontSize: 12 }}>No nodes registered yet.</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {status.llm_nodes.map(n => (
              <NodeRow key={n.node} node={n} />
            ))}
          </div>
        )}
      </div>

      {/* Plan info */}
      <div className="card" style={{ marginTop: 8 }}>
        <div style={{ fontSize: 11, color: 'var(--muted)', fontFamily: 'var(--mono)', marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          Account
        </div>
        <div style={{ display: 'flex', gap: 24, alignItems: 'center', flexWrap: 'wrap' }}>
          <KV label="Email" value={me?.user?.email} />
          <KV label="Plan" value={<span className={`tag ${me?.user?.plan === 'free' ? 'tag-gray' : 'tag-green'}`}>{me?.user?.plan}</span>} />
          <KV label="User ID" value={<span style={{ fontFamily: 'var(--mono)', fontSize: 11 }}>{me?.user?.id?.slice(0, 8)}…</span>} />
        </div>
      </div>
    </div>
  )
}

function StatCard({ label, value, isStatus }) {
  const isOk = value === 'ok' || value === 1 || (typeof value === 'number')
  return (
    <div className="card fade-up">
      <div style={{ fontSize: 11, color: 'var(--muted)', fontFamily: 'var(--mono)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8 }}>
        {label}
      </div>
      <div style={{ fontSize: 24, fontWeight: 800, letterSpacing: '-1px', display: 'flex', alignItems: 'center', gap: 8 }}>
        {isStatus ? (
          <>
            <span className={`dot dot-pulse ${value === 'ok' ? 'dot-green' : 'dot-red'}`} />
            <span style={{ color: value === 'ok' ? 'var(--accent)' : 'var(--danger)', fontSize: 16 }}>
              {value}
            </span>
          </>
        ) : (
          <span>{value}</span>
        )}
      </div>
    </div>
  )
}

function NodeRow({ node }) {
  const latency = node.avg_latency_ms
  const latencyColor = latency > 600 ? 'var(--danger)' : latency > 300 ? 'var(--warn)' : 'var(--accent)'

  return (
    <div className="card" style={{
      display: 'flex', alignItems: 'center', gap: 16,
      padding: '12px 16px',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 120 }}>
        <span className={`dot ${node.healthy ? 'dot-green dot-pulse' : 'dot-red'}`} />
        <span style={{ fontFamily: 'var(--mono)', fontSize: 12 }}>{node.node}</span>
      </div>

      <div style={{ flex: 1, display: 'flex', gap: 20, flexWrap: 'wrap' }}>
        <KV label="Status" value={
          <span className={`tag ${node.healthy ? 'tag-green' : 'tag-red'}`}>
            {node.healthy ? 'healthy' : 'down'}
          </span>
        } />
        <KV label="In flight" value={
          <span style={{ fontFamily: 'var(--mono)', fontSize: 13 }}>{node.in_flight}</span>
        } />
        <KV label="Avg latency" value={
          <span style={{ fontFamily: 'var(--mono)', fontSize: 13, color: latencyColor }}>
            {latency ? `${latency}ms` : '—'}
          </span>
        } />
      </div>

      <div style={{ fontSize: 11, color: 'var(--muted)', fontFamily: 'var(--mono)', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {node.url}
      </div>
    </div>
  )
}

function KV({ label, value }) {
  return (
    <div>
      <div style={{ fontSize: 10, color: 'var(--muted)', fontFamily: 'var(--mono)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>
        {label}
      </div>
      <div>{value}</div>
    </div>
  )
}
