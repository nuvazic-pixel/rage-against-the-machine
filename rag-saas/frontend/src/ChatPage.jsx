import { useState, useEffect, useRef } from 'react'
import { api } from './api.js'
import ReactMarkdown from 'react-markdown'

export default function ChatPage() {
  const [sessions, setSessions] = useState([])
  const [sessionId, setSessionId] = useState(null)
  const [messages, setMessages] = useState([])
  const [collections, setCollections] = useState([])
  const [collectionId, setCollectionId] = useState('')
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const bottomRef = useRef(null)

  useEffect(() => {
    api.getSessions().then(setSessions).catch(() => {})
    api.getCollections().then(setCollections).catch(() => {})
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const loadSession = async (id) => {
    setSessionId(id)
    const msgs = await api.getMessages(id)
    setMessages(msgs)
  }

  const newSession = async () => {
    const s = await api.createSession(collectionId || null, 'New Chat')
    setSessions(prev => [s, ...prev])
    setSessionId(s.id)
    setMessages([])
  }

  const send = async (e) => {
    e.preventDefault()
    if (!query.trim() || loading) return
    const q = query.trim()
    setQuery('')
    setError('')
    setLoading(true)

    // Optimistic user message
    const userMsg = { role: 'user', content: q, id: Date.now() }
    setMessages(prev => [...prev, userMsg])

    try {
      // Create session if none
      let sid = sessionId
      if (!sid) {
        const s = await api.createSession(collectionId || null, q.slice(0, 60))
        setSessions(prev => [s, ...prev])
        setSessionId(s.id)
        sid = s.id
      }

      const res = await api.ask(q, collectionId || null, sid)
      const assistantMsg = {
        role: 'assistant', content: res.answer,
        sources: res.sources, id: Date.now() + 1,
        remaining: res.queries_remaining,
      }
      setMessages(prev => [...prev, assistantMsg])

      // Refresh session list (title may have updated)
      api.getSessions().then(setSessions).catch(() => {})
    } catch (err) {
      setError(err.message)
      setMessages(prev => prev.slice(0, -1)) // remove optimistic
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
      {/* Session list */}
      <div style={{
        width: 220, flexShrink: 0, borderRight: '1px solid var(--border)',
        display: 'flex', flexDirection: 'column', overflow: 'hidden',
      }}>
        <div style={{ padding: '12px 12px 8px', borderBottom: '1px solid var(--border)' }}>
          <button className="btn btn-ghost btn-sm" style={{ width: '100%' }} onClick={newSession}>
            + New chat
          </button>
        </div>

        {/* Collection selector */}
        <div style={{ padding: '8px 12px', borderBottom: '1px solid var(--border)' }}>
          <select
            value={collectionId}
            onChange={e => setCollectionId(e.target.value)}
            style={{
              width: '100%', background: 'var(--surface2)', border: '1px solid var(--border)',
              borderRadius: 'var(--radius)', color: 'var(--text)', fontSize: 12,
              padding: '6px 8px', fontFamily: 'var(--sans)',
            }}
          >
            <option value="">All collections</option>
            {collections.map(c => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '8px' }}>
          {sessions.map(s => (
            <button key={s.id} onClick={() => loadSession(s.id)} style={{
              width: '100%', textAlign: 'left', background: sessionId === s.id ? '#1a2a0020' : 'transparent',
              border: sessionId === s.id ? '1px solid #2a4000' : '1px solid transparent',
              borderRadius: 'var(--radius)', color: sessionId === s.id ? 'var(--text)' : 'var(--muted)',
              padding: '7px 10px', cursor: 'pointer', fontSize: 12, marginBottom: 2,
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              fontFamily: 'var(--sans)',
            }}>
              {s.title}
            </button>
          ))}
        </div>
      </div>

      {/* Chat area */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Messages */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '24px 32px', display: 'flex', flexDirection: 'column', gap: 20 }}>
          {messages.length === 0 && (
            <div style={{
              flex: 1, display: 'flex', flexDirection: 'column',
              alignItems: 'center', justifyContent: 'center', color: 'var(--muted)',
            }}>
              <div style={{ fontSize: 32, marginBottom: 12 }}>◈</div>
              <div style={{ fontWeight: 700, fontSize: 16, color: 'var(--text)', marginBottom: 6 }}>
                Ask anything
              </div>
              <div style={{ fontSize: 12, maxWidth: 280, textAlign: 'center', lineHeight: 1.6 }}>
                Answers come only from your documents. No hallucination.
              </div>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={msg.id || i} className="fade-up" style={{
              display: 'flex', gap: 12, alignItems: 'flex-start',
            }}>
              {/* Avatar */}
              <div style={{
                width: 28, height: 28, flexShrink: 0, borderRadius: 4,
                background: msg.role === 'user' ? 'var(--surface2)' : '#1a2a0040',
                border: `1px solid ${msg.role === 'user' ? 'var(--border)' : '#2a4000'}`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 11, fontFamily: 'var(--mono)',
                color: msg.role === 'user' ? 'var(--muted)' : 'var(--accent)',
              }}>
                {msg.role === 'user' ? 'U' : 'AI'}
              </div>

              <div style={{ flex: 1, minWidth: 0 }}>
                {/* Content */}
                <div style={{
                  fontSize: 14, lineHeight: 1.7,
                  color: msg.role === 'user' ? 'var(--muted)' : 'var(--text)',
                }}>
                  {msg.role === 'assistant' ? (
                    <ReactMarkdown>{msg.content}</ReactMarkdown>
                  ) : (
                    <span>{msg.content}</span>
                  )}
                </div>

                {/* Sources */}
                {msg.sources?.length > 0 && (
                  <div style={{ marginTop: 10, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {msg.sources.map((s, si) => (
                      <SourceChip key={si} source={s} />
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}

          {loading && (
            <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }} className="fade-up">
              <div style={{
                width: 28, height: 28, flexShrink: 0, borderRadius: 4,
                background: '#1a2a0040', border: '1px solid #2a4000',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 11, fontFamily: 'var(--mono)', color: 'var(--accent)',
              }}>AI</div>
              <div style={{ display: 'flex', gap: 4, alignItems: 'center', paddingTop: 6 }}>
                {[0, 1, 2].map(n => (
                  <div key={n} style={{
                    width: 5, height: 5, borderRadius: '50%',
                    background: 'var(--accent)', opacity: 0.6,
                    animation: `pulse 1.2s ${n * 0.2}s infinite`,
                  }} />
                ))}
              </div>
            </div>
          )}

          {error && (
            <div style={{
              color: 'var(--danger)', fontSize: 12, padding: '8px 12px',
              background: '#2a000020', borderRadius: 'var(--radius)',
              border: '1px solid #4a000030',
            }}>
              {error}
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div style={{
          padding: '16px 32px', borderTop: '1px solid var(--border)',
          background: 'var(--surface)',
        }}>
          <form onSubmit={send} style={{ display: 'flex', gap: 8 }}>
            <input
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Ask a question about your documents…"
              style={{ flex: 1 }}
              disabled={loading}
            />
            <button type="submit" className="btn btn-primary" disabled={loading || !query.trim()}>
              Ask
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}

function SourceChip({ source }) {
  const [open, setOpen] = useState(false)
  const name = source.metadata?.filename || 'source'
  return (
    <div style={{ position: 'relative' }}>
      <button onClick={() => setOpen(!open)} style={{
        background: 'var(--surface2)', border: '1px solid var(--border)',
        borderRadius: 3, color: 'var(--muted)', fontSize: 11,
        padding: '2px 8px', cursor: 'pointer', fontFamily: 'var(--mono)',
        transition: 'all 0.1s',
      }}
      onMouseEnter={e => e.target.style.borderColor = 'var(--border2)'}
      onMouseLeave={e => e.target.style.borderColor = 'var(--border)'}
      >
        ⊡ {name} {source.score ? `· ${source.score}` : ''}
      </button>
      {open && (
        <div style={{
          position: 'absolute', bottom: '100%', left: 0, marginBottom: 4,
          width: 320, background: 'var(--surface)', border: '1px solid var(--border2)',
          borderRadius: 'var(--radius)', padding: 12, zIndex: 100,
          boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
        }}>
          <div style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--muted)', marginBottom: 6 }}>
            {name} · chunk {source.metadata?.chunk_index ?? '?'}
          </div>
          <div style={{ fontSize: 12, lineHeight: 1.6, color: 'var(--text)' }}>
            {source.text}
          </div>
        </div>
      )}
    </div>
  )
}
