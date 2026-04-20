const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8001'

function getToken() {
  return localStorage.getItem('token')
}

async function request(path, options = {}) {
  const token = getToken()
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
  })
  if (res.status === 401) {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    window.location.href = '/login'
    return
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
  }
  if (res.status === 204) return null
  return res.json()
}

export const api = {
  // Auth
  register: (email, password) =>
    request('/auth/register', { method: 'POST', body: JSON.stringify({ email, password }) }),
  login: (email, password) =>
    request('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }),
  me: () => request('/me'),

  // Collections
  getCollections: () => request('/collections'),
  createCollection: (name, description) =>
    request('/collections', { method: 'POST', body: JSON.stringify({ name, description }) }),
  deleteCollection: (id) =>
    request(`/collections/${id}`, { method: 'DELETE' }),

  // Documents
  getDocuments: (collectionId) =>
    request(`/documents${collectionId ? `?collection_id=${collectionId}` : ''}`),
  uploadDocument: (collectionId, file) => {
    const form = new FormData()
    form.append('collection_id', collectionId)
    form.append('file', file)
    const token = getToken()
    return fetch(`${BASE}/documents`, {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
    }).then(async res => {
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }))
        throw new Error(err.detail || 'Upload failed')
      }
      return res.json()
    })
  },
  getDocument: (id) => request(`/documents/${id}`),
  deleteDocument: (id) => request(`/documents/${id}`, { method: 'DELETE' }),

  // Chat
  getSessions: () => request('/chat/sessions'),
  createSession: (collectionId, title) =>
    request('/chat/sessions', { method: 'POST', body: JSON.stringify({ collection_id: collectionId, title }) }),
  getMessages: (sessionId) => request(`/chat/sessions/${sessionId}/messages`),
  ask: (query, collectionId, sessionId) =>
    request('/chat/ask', {
      method: 'POST',
      body: JSON.stringify({ query, collection_id: collectionId, session_id: sessionId }),
    }),
  searchDebug: (q, collectionId) =>
    request(`/chat/search?q=${encodeURIComponent(q)}${collectionId ? `&collection_id=${collectionId}` : ''}`),

  // System
  status: () => request('/status'),
}
