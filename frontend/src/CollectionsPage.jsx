import { useState, useEffect } from 'react'
import { api } from './api.js'

export default function CollectionsPage() {
  const [collections, setCollections] = useState([])
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const [creating, setCreating] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [error, setError] = useState('')

  const load = () => api.getCollections().then(setCollections).catch(() => {})
  useEffect(() => { load() }, [])

  const create = async (e) => {
    e.preventDefault()
    if (!name.trim()) return
    setCreating(true); setError('')
    try {
      await api.createCollection(name.trim(), desc.trim())
      setName(''); setDesc(''); setShowForm(false)
      load()
    } catch (err) {
      setError(err.message)
    } finally {
      setCreating(false)
    }
  }

  const remove = async (id, colName) => {
    if (!confirm(`Delete "${colName}" and all its documents?`)) return
    await api.deleteCollection(id).catch(() => {})
    load()
  }

  return (
    <div style={{ padding: '28px 32px', height: '100%', overflowY: 'auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 800, letterSpacing: '-0.5px' }}>Collections</h1>
          <div style={{ color: 'var(--muted)', fontSize: 12, marginTop: 2 }}>
            Group documents into searchable collections
          </div>
        </div>
        <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
          {showForm ? 'Cancel' : '+ New collection'}
        </button>
      </div>

      {/* Create form */}
      {showForm && (
        <div className="card fade-up" style={{ marginBottom: 24 }}>
          <h3 style={{ fontSize: 14, fontWeight: 700, marginBottom: 14 }}>New collection</h3>
          <form onSubmit={create} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <input placeholder="Name (e.g. Research Q3)" value={name} onChange={e => setName(e.target.value)} required />
            <input placeholder="Description (optional)" value={desc} onChange={e => setDesc(e.target.value)} />
            {error && <div style={{ color: 'var(--danger)', fontSize: 12 }}>{error}</div>}
            <div style={{ display: 'flex', gap: 8 }}>
              <button type="submit" className="btn btn-primary btn-sm" disabled={creating}>
                {creating ? 'Creating…' : 'Create'}
              </button>
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => setShowForm(false)}>
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Grid */}
      {collections.length === 0 ? (
        <EmptyState />
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 14 }}>
          {collections.map(c => (
            <div key={c.id} className="card fade-up" style={{
              display: 'flex', flexDirection: 'column', gap: 10,
              transition: 'border-color 0.15s',
            }}
            onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--border2)'}
            onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--border)'}
            >
              <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
                <div style={{
                  width: 36, height: 36, borderRadius: 4,
                  background: '#1a2a0030', border: '1px solid #2a4000',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 16, color: 'var(--accent)',
                }}>⬡</div>
                <button className="btn btn-danger btn-sm" onClick={() => remove(c.id, c.name)}>
                  ×
                </button>
              </div>
              <div>
                <div style={{ fontWeight: 700, fontSize: 14 }}>{c.name}</div>
                {c.description && (
                  <div style={{ color: 'var(--muted)', fontSize: 12, marginTop: 2, lineHeight: 1.4 }}>
                    {c.description}
                  </div>
                )}
              </div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 4 }}>
                <span className="tag tag-gray">{c.doc_count ?? 0} docs</span>
                <span style={{ color: 'var(--muted)', fontSize: 11, fontFamily: 'var(--mono)' }}>
                  {new Date(c.created_at).toLocaleDateString()}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function EmptyState() {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      minHeight: 300, color: 'var(--muted)', textAlign: 'center',
    }}>
      <div style={{ fontSize: 36, marginBottom: 12 }}>⬡</div>
      <div style={{ fontWeight: 700, color: 'var(--text)', marginBottom: 6 }}>No collections yet</div>
      <div style={{ fontSize: 12, maxWidth: 240, lineHeight: 1.6 }}>
        Create a collection to start uploading and querying documents.
      </div>
    </div>
  )
}
