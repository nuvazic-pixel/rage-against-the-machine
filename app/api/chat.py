import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.services.auth import current_user
from app.services.retrieval import retrieve, build_context
from app.services.llm_router import get_router
from app.utils.cache import check_rate_limit
from app.db.postgres import get_pool
from app.config import get_settings

router = APIRouter(prefix="/chat", tags=["chat"])

SYSTEM_PROMPT = """You are a strict retrieval-based assistant.

MANDATORY RULES:
- Answer ONLY using the provided context below.
- If the answer is not explicitly present in the context, reply EXACTLY:
  "I don't know based on the provided documents."
- Do NOT infer, assume, or use prior knowledge.
- Do NOT hallucinate facts.
- Quote relevant phrases from context when possible.
- Keep answers concise (max 4 sentences).
- If multiple sources support the answer, mention them."""


class AskBody(BaseModel):
    query: str
    collection_id: str | None = None
    session_id: str | None = None


class SessionCreate(BaseModel):
    collection_id: str | None = None
    title: str = "New Chat"


# ─────────────────────────────────────────
# Sessions
# ─────────────────────────────────────────

@router.get("/sessions")
async def list_sessions(user=Depends(current_user)):
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT id, title, collection_id, created_at, updated_at
        FROM chat_sessions
        WHERE user_id = $1
        ORDER BY updated_at DESC
        LIMIT 50
        """,
        user["id"],
    )
    return [dict(r) for r in rows]


@router.post("/sessions", status_code=201)
async def create_session(body: SessionCreate, user=Depends(current_user)):
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO chat_sessions (user_id, collection_id, title)
        VALUES ($1, $2, $3)
        RETURNING id, title, collection_id, created_at
        """,
        user["id"], body.collection_id, body.title,
    )
    return dict(row)


@router.get("/sessions/{session_id}/messages")
async def get_messages(session_id: str, user=Depends(current_user)):
    pool = await get_pool()
    # Verify ownership
    sess = await pool.fetchrow(
        "SELECT id FROM chat_sessions WHERE id = $1 AND user_id = $2",
        session_id, user["id"],
    )
    if not sess:
        raise HTTPException(404, "Session not found")

    rows = await pool.fetch(
        "SELECT id, role, content, sources, created_at FROM messages WHERE session_id = $1 ORDER BY id",
        session_id,
    )
    return [dict(r) for r in rows]


# ─────────────────────────────────────────
# Ask
# ─────────────────────────────────────────

@router.post("/ask")
async def ask(body: AskBody, user=Depends(current_user)):
    if not body.query.strip():
        raise HTTPException(400, "Query cannot be empty")

    # Rate limiting
    allowed, remaining = await check_rate_limit(user["id"], user["plan"])
    if not allowed:
        raise HTTPException(
            429,
            detail=f"Daily query limit reached for {user['plan']} plan. Upgrade for more queries.",
        )

    # Retrieve docs
    docs = await retrieve(
        query=body.query,
        user_id=user["id"],
        collection_id=body.collection_id,
    )

    if not docs:
        answer = "I don't know based on the provided documents."
        sources = []
    else:
        context = build_context(docs)
        llm = get_router()
        answer = await llm.generate(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {body.query}"},
            ],
            temperature=0.0,
            max_tokens=300,
        )
        sources = [
            {
                "text": d["text"][:200],
                "metadata": d["metadata"],
                "score": round(d.get("cross_score", d.get("fused_score", 0)), 3),
            }
            for d in docs
        ]

    # Persist to session if provided
    if body.session_id:
        pool = await get_pool()
        sess = await pool.fetchrow(
            "SELECT id FROM chat_sessions WHERE id = $1 AND user_id = $2",
            body.session_id, user["id"],
        )
        if sess:
            await pool.executemany(
                "INSERT INTO messages (session_id, role, content, sources) VALUES ($1, $2, $3, $4::jsonb)",
                [
                    (body.session_id, "user", body.query, "[]"),
                    (body.session_id, "assistant", answer, json.dumps(sources)),
                ],
            )
            await pool.execute(
                "UPDATE chat_sessions SET updated_at = now(), title = COALESCE(NULLIF(title, 'New Chat'), $1) WHERE id = $2",
                body.query[:60], body.session_id,
            )

    return {
        "answer": answer,
        "sources": sources,
        "queries_remaining": remaining,
    }


# ─────────────────────────────────────────
# Debug search (no LLM, raw retrieval results)
# ─────────────────────────────────────────

@router.get("/search")
async def debug_search(
    q: str,
    collection_id: str | None = None,
    user=Depends(current_user),
):
    docs = await retrieve(query=q, user_id=user["id"], collection_id=collection_id)
    return {"query": q, "results": docs}
