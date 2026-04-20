-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- ─────────────────────────────────────────
-- Users (multi-tenant SaaS)
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email       TEXT UNIQUE NOT NULL,
    hashed_pw   TEXT NOT NULL,
    plan        TEXT NOT NULL DEFAULT 'free',  -- free | pro | enterprise
    created_at  TIMESTAMPTZ DEFAULT now(),
    is_active   BOOLEAN DEFAULT TRUE
);

-- ─────────────────────────────────────────
-- Collections (per-user document groups)
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS collections (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    description TEXT,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- ─────────────────────────────────────────
-- Documents
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS documents (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    collection_id  UUID NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    user_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename       TEXT NOT NULL,
    file_type      TEXT NOT NULL,
    char_count     INT DEFAULT 0,
    chunk_count    INT DEFAULT 0,
    status         TEXT NOT NULL DEFAULT 'processing',  -- processing | ready | error
    error_msg      TEXT,
    created_at     TIMESTAMPTZ DEFAULT now()
);

-- ─────────────────────────────────────────
-- Chunks (the core search table)
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chunks (
    id              BIGSERIAL PRIMARY KEY,
    document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    collection_id   UUID NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    chunk_index     INT NOT NULL,
    text            TEXT NOT NULL,
    embedding       vector(384),
    metadata        JSONB DEFAULT '{}',
    UNIQUE (document_id, chunk_index)
);

-- Fast ANN search
CREATE INDEX IF NOT EXISTS chunks_embedding_idx
    ON chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Filter by user/collection
CREATE INDEX IF NOT EXISTS chunks_user_collection_idx
    ON chunks (user_id, collection_id);

-- ─────────────────────────────────────────
-- Chat sessions
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chat_sessions (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    collection_id  UUID REFERENCES collections(id) ON DELETE SET NULL,
    title          TEXT DEFAULT 'New Chat',
    created_at     TIMESTAMPTZ DEFAULT now(),
    updated_at     TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS messages (
    id          BIGSERIAL PRIMARY KEY,
    session_id  UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role        TEXT NOT NULL,  -- user | assistant
    content     TEXT NOT NULL,
    sources     JSONB DEFAULT '[]',
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- ─────────────────────────────────────────
-- Usage tracking (for SaaS plans)
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS usage_log (
    id          BIGSERIAL PRIMARY KEY,
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    action      TEXT NOT NULL,  -- query | upload | chunk
    tokens_used INT DEFAULT 0,
    created_at  TIMESTAMPTZ DEFAULT now()
);
