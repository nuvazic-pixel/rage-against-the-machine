import { useState, useEffect, useRef } from 'react'
import { api } from './api.js'

const STATUS_TAG = {
  ready:      { cls: 'tag-green',  label: 'ready' },
  processing: { cls: 'tag-yellow', label: 'processing' },
  error:      { cls: 'tag-red',    label: 'error' },
}

export default function DocumentsPage() {
  const [docs, setDocs] = useState([])
  const [collections, setCollections] = useState([])
  const [collectionId, setCollectionId] = useState('')
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const fileRef = useRef()

  const load = () =>
    api.getDocuments(collectionId || null).then(setDocs).catch(() => {})

  useEffect(() => {
    api.getCollections().then(cols => {
      setCollections(cols)
      if (cols.length > 0 && !collectionId) setCollectionId(cols[0].id)
    }).catch(() => {})
  }, [])

  useEffect(() => { load() }, [collectionId])

  // Poll processing docs
  useEffect(() => {
    const processing = docs.filter(d => d.status === 'processing')
    if (processing.length === 0) return
    const t = setInterval(load, 3000)
    return () => clearInterval(t)
  }, [docs, collectionId])

  const upload = async (files) => {
    if (!collectionId) { setUploadError('Select a collection first'); return }
    if (!files?.length) return
    setUploadError('')
    for (const file of files) {
      setUploading(true)
      try {
        await api.uploadDocument(collectionId, file)
        load()
      } catch (err) {
        setUploadError(err.message)
      } finally {
        setUploading(false)
      }
    }
  }

  const remove = async (id, filename) => {
    if (!confirm(`Delete "${filename}"?`)) return
    await api.deleteDocument(id).catch(() => {})
    load()
  }

  const onDrop = (e) => {
    e.preventDefault(); setDragOver(false)
    upload(Array.from(e.dataTransfer.files))
  }

  return (
    <div style={{ padding: '28px 32px', height: '100%', overflowY: 'auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 800, letterSpacing: '-0.5px' }}>Documents</h1>
          <div style={{ color: 'var(--muted)', fontSize: 12, marginTop: 2 }}>
            .txt · .md · .py · .json · .csv · .pdf
          </div>
        </div>

        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <select
            value={collectionId}
            onChange={e => setCollectionId(e.target.value)}
            style={{
              background: 'var(--surface2)', border: '1px solid var(--border)',
              borderRadius: 'var(--radius)', color: 'var(--text)', fontSize: 13,
              padding: '7px 10px', fontFamily: 'var(--sans)',
            }}
          >
            <option value="">All</option>
            {collections.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <button className="btn btn-primary" onClick={() => fileRef.current?.click()} disabled={uploading}>
            {uploading ? 'Uploading…' : '↑ Upload'}
          </button>
          <input ref={fileRef} type="file" multiple hidden
            accept=".txt,.md,.py,.js,.ts,.json,.csv,.yaml,.yml,.pdf"
            onChange={e => upload(Array.from(e.target.files))}
          />
        </div>
      </div>

      {uploadError && (
        <div style={{
          color: 'var(--danger)', fontSize: 12, padding: '8px 12px', marginBottom: 16,
          background: '#2a000020', borderRadius: 'var(--radius)', border: '1px solid #4a000030',
        }}>{uploadError}</div>
      )}

      {/* Drop zone */}
      <div
        onDragOver={e => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        style={{
          border: `2px dashed ${dragOver ? 'var(--accent)' : 'var(--border)'}`,
          borderRadius: 'var(--radius)', padding: '24px', marginBottom: 20,
          textAlign: 'center', color: dragOver ? 'var(--accent)' : 'var(--muted)',
          transition: 'all 0.15s', cursor: 'pointer', fontSize: 13,
          background: dragOver ? '#1a2a0010' : 'transparent',
        }}
        onClick={() => fileRef.current?.click()}
      >
        Drop files here or click to upload
      </div>

      {/* Table */}
      {docs.length === 0 ? (
        <div style={{ color: 'var(--muted)', textAlign: 'center', padding: 40, fontSize: 13 }}>
          No documents yet. Upload some files to get started.
        </div>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border)' }}>
              {['File', 'Type', 'Chunks', 'Status', 'Uploaded', ''].map(h => (
                <th key={h} style={{
                  textAlign: 'left', padding: '6px 12px',
                  color: 'var(--muted)', fontSize: 11, fontWeight: 600,
                  fontFamily: 'var(--mono)', textTransform: 'uppercase', letterSpacing: '0.05em',
                }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {docs.map(d => {
              const tag = STATUS_TAG[d.status] || STATUS_TAG.processing
              return (
                <tr key={d.id} style={{ borderBottom: '1px solid var(--border)' }}
                  onMouseEnter={e => e.currentTarget.style.background = 'var(--surface2)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                >
                  <td style={{ padding: '10px 12px', fontSize: 13, fontWeight: 500 }}>
                    {d.filename}
                  </td>
                  <td style={{ padding: '10px 12px' }}>
                    <span className="tag tag-gray">{d.file_type}</span>
                  </td>
                  <td style={{ padding: '10px 12px', fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--muted)' }}>
                    {d.chunk_count || '—'}
                  </td>
                  <td style={{ padding: '10px 12px' }}>
                    <span className={`tag ${tag.cls}`}>
                      {d.status === 'processing' && <span style={{ animation: 'pulse 1s infinite', marginRight: 4 }}>●</span>}
                      {tag.label}
                    </span>
                  </td>
                  <td style={{ padding: '10px 12px', color: 'var(--muted)', fontSize: 12, fontFamily: 'var(--mono)' }}>
                    {new Date(d.created_at).toLocaleDateString()}
                  </td>
                  <td style={{ padding: '10px 12px' }}>
                    <button className="btn btn-danger btn-sm" onClick={() => remove(d.id, d.filename)}>×</button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}
