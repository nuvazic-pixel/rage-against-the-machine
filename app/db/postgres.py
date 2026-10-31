import asyncpg
import json
import math
from uuid import UUID
from app.config import get_settings

_pool: asyncpg.Pool | None = None


def vector_literal(values: list[float]) -> str:
    """No custom pgvector codec is registered: bind its finite text format."""
    if type(values) is not list or not values or any(type(value) not in (int, float) or not math.isfinite(value) for value in values):
        raise ValueError("Embedding must be a non-empty finite numeric vector")
    return json.dumps(values, allow_nan=False, separators=(",", ":"))


def uuid_value(value):
    return value if isinstance(value, UUID) else UUID(value)


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
        uuid_value(document_id), uuid_value(collection_id), uuid_value(user_id),
        chunk_index, text, vector_literal(embedding), json.dumps(metadata, allow_nan=False),
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
            vector_literal(query_embedding), uuid_value(user_id), uuid_value(collection_id), top_k,
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
            vector_literal(query_embedding), uuid_value(user_id), top_k,
        )

    return [
        {
            "id": r["id"],
            "text": r["text"],
            "metadata": json.loads(r["metadata"]) if isinstance(r["metadata"], str) else dict(r["metadata"] or {}),
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
        status, chunk_count, char_count, error_msg, uuid_value(doc_id),
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
            uuid_value(user_id), uuid_value(collection_id),
        )
    else:
        rows = await pool.fetch(
            "SELECT id, text FROM chunks WHERE user_id = $1",
            uuid_value(user_id),
        )
    return [{"id": r["id"], "text": r["text"]} for r in rows]
