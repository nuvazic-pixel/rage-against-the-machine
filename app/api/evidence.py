"""Read-only, collection-scoped evidence for external orchestrators."""
from datetime import datetime, timezone
from hashlib import sha256
import math
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db.postgres import get_pool
from app.services.auth import current_user
from app.utils.cache import check_rate_limit

router = APIRouter(prefix="/chat", tags=["evidence"])


async def retrieve_fresh(query, user_id, collection_id):
    # Lazy import: contract tests do not load/download embedding/reranker models.
    from app.services.retrieval import retrieve
    return await retrieve(query=query, user_id=user_id, collection_id=collection_id, use_cache=False)


@router.get("/evidence")
async def evidence(q: str = Query(min_length=1, max_length=2000),
                   collection_id: UUID = Query(...),
                   user=Depends(current_user)):
    if not q.strip():
        raise HTTPException(422, "Query and collection must be non-empty")
    pool = await get_pool()
    collection = await pool.fetchrow(
        "SELECT id FROM collections WHERE id = $1 AND user_id = $2", collection_id, UUID(user["id"]))
    if collection is None:
        raise HTTPException(404, "Collection not found")
    allowed, remaining = await check_rate_limit(user["id"], user["plan"])
    if not allowed:
        raise HTTPException(429, "Daily retrieval budget exhausted")
    docs = await retrieve_fresh(q, user["id"], str(collection_id))
    results = []
    for doc in docs:
        body = doc["text"]
        if type(body) is not str or not body.strip():
            continue
        score = float(doc.get("cross_score", doc.get("fused_score", 0)))
        results.append({"chunk_id": str(doc["id"]), "document_id": str(doc["document_id"]),
                        "text": body, "sha256": sha256(body.encode("utf-8")).hexdigest(),
                        "score": score if math.isfinite(score) else None})
    return {"schema_version": "eaon.evidence.v1", "query": q,
            "owner_id": str(user["id"]), "collection_id": str(collection_id),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "cache": "bypassed", "authority": "candidate_only", "queries_remaining": remaining, "results": results}
