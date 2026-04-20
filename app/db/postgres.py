import asyncpg
from app.config import get_settings

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        raise RuntimeError("DB pool not initialized. Call init_db() at startup.")
    return _pool


async def init_db() -> None:
    global _pool
    cfg = get_settings()
    _pool = await asyncpg.create_pool(
        host=cfg.db_host,
        port=cfg.db_port,
        user=cfg.db_user,
        password=cfg.db_password,
        database=cfg.db_name,
        min_size=5,
        max_size=20,
        command_timeout=30,
    )


async def close_db() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


# ─────────────────────────────────────────
# Chunk queries
# ─────────────────────────────────────────

async def insert_chunk(
    document_id: str,
    collection_id: str,
    user_id: str,
    chunk_index: int,
    text: str,
    embedding: list[float],
    metadata: dict,
) -> None:
    pool = await get_pool()
    await pool.execute(
        """
        INSERT INTO chunks
            (document_id, collection_id, user_id, chunk_index, text, embedding, metadata)
        VALUES ($1, $2, $3, $4, $5, $6::vector, $7::jsonb)
        ON CONFLICT (document_id, chunk_index) DO UPDATE
            SET text = EXCLUDED.text,
                embedding = EXCLUDED.embedding,
                metadata = EXCLUDED.metadata
        """,
        document_id, collection_id, user_id,
        chunk_index, text, embedding, metadata,
    )


async def vector_search(
    query_embedding: list[float],
    user_id: str,
    collection_id: str | None,
    top_k: int = 50,
) -> list[dict]:
    pool = await get_pool()

    if collection_id:
        rows = await pool.fetch(
            """
            SELECT id, text, metadata, document_id,
                   embedding <=> $1::vector AS distance
            FROM chunks
            WHERE user_id = $2 AND collection_id = $3
            ORDER BY embedding <=> $1::vector
            LIMIT $4
            """,
            query_embedding, user_id, collection_id, top_k,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT id, text, metadata, document_id,
                   embedding <=> $1::vector AS distance
            FROM chunks
            WHERE user_id = $2
            ORDER BY embedding <=> $1::vector
            LIMIT $3
            """,
            query_embedding, user_id, top_k,
        )

    return [
        {
            "id": r["id"],
            "text": r["text"],
            "metadata": dict(r["metadata"]) if r["metadata"] else {},
            "document_id": str(r["document_id"]),
            "distance": float(r["distance"]),
        }
        for r in rows
    ]


async def update_document_status(
    doc_id: str,
    status: str,
    chunk_count: int = 0,
    char_count: int = 0,
    error_msg: str | None = None,
) -> None:
    pool = await get_pool()
    await pool.execute(
        """
        UPDATE documents
        SET status = $1, chunk_count = $2, char_count = $3, error_msg = $4
        WHERE id = $5
        """,
        status, chunk_count, char_count, error_msg, doc_id,
    )


async def get_collection_chunks_for_bm25(
    user_id: str,
    collection_id: str | None,
) -> list[dict]:
    """Fetch all chunk texts + IDs for BM25 index building."""
    pool = await get_pool()
    if collection_id:
        rows = await pool.fetch(
            "SELECT id, text FROM chunks WHERE user_id = $1 AND collection_id = $2",
            user_id, collection_id,
        )
    else:
        rows = await pool.fetch(
            "SELECT id, text FROM chunks WHERE user_id = $1",
            user_id,
        )
    return [{"id": r["id"], "text": r["text"]} for r in rows]
