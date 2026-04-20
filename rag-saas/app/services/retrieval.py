"""
Retrieval pipeline:
  1. Vector search (pgvector, top_k=50)
  2. BM25 fusion (global corpus, aligned by doc ID)
  3. Score normalization + weighted fusion
  4. CrossEncoder reranking (top 5 → top 3)
"""
import json
from rank_bm25 import BM25Okapi

from app.config import get_settings
from app.db.postgres import vector_search, get_collection_chunks_for_bm25
from app.services.embedding import embed_text
from app.services.reranker import rerank_docs
from app.utils.text import tokenize, min_max_normalize
from app.utils.cache import get_cached_search, set_cached_search
import structlog

log = structlog.get_logger()


async def retrieve(
    query: str,
    user_id: str,
    collection_id: str | None = None,
) -> list[dict]:
    """
    Full hybrid retrieval. Returns top-k ranked chunks.
    Uses Redis cache — identical queries within TTL are free.
    """
    cfg = get_settings()

    # ── 1. Cache check
    cached = await get_cached_search(query, user_id)
    if cached is not None:
        log.debug("cache_hit", user=user_id)
        return cached

    # ── 2. Embed query
    query_emb = await embed_text(query)

    # ── 3. Vector search
    vec_results = await vector_search(
        query_embedding=query_emb,
        user_id=user_id,
        collection_id=collection_id,
        top_k=cfg.vector_top_k,
    )

    if not vec_results:
        return []

    # ── 4. BM25 over full user corpus
    corpus = await get_collection_chunks_for_bm25(user_id, collection_id)

    # Map chunk_id → BM25 index position
    id_to_idx: dict[int, int] = {doc["id"]: i for i, doc in enumerate(corpus)}

    tokenized_corpus = [tokenize(doc["text"]) for doc in corpus]
    bm25 = BM25Okapi(tokenized_corpus)
    bm25_all = bm25.get_scores(tokenize(query))

    # ── 5. Normalize + fuse scores
    distances = [d["distance"] for d in vec_results]
    vec_scores = [1.0 - x for x in min_max_normalize(distances)]

    candidate_bm25_raw = []
    for doc in vec_results:
        idx = id_to_idx.get(doc["id"])
        if idx is not None:
            candidate_bm25_raw.append(float(bm25_all[idx]))
        else:
            candidate_bm25_raw.append(0.0)

    bm25_scores_norm = min_max_normalize(candidate_bm25_raw)

    for i, doc in enumerate(vec_results):
        doc["fused_score"] = (
            cfg.vector_weight * vec_scores[i]
            + cfg.bm25_weight * bm25_scores_norm[i]
        )

    # ── 6. Take top 5 for reranking
    top5 = sorted(vec_results, key=lambda d: d["fused_score"], reverse=True)[: cfg.rerank_top_n]

    # ── 7. CrossEncoder rerank → top 3
    reranked = await rerank_docs(query, top5)
    final = reranked[: cfg.final_top_k]

    # ── 8. Cache and return
    await set_cached_search(query, user_id, final)
    return final


def build_context(docs: list[dict], max_chars: int | None = None) -> str:
    cfg = get_settings()
    limit = max_chars or cfg.max_context_chars
    context = ""
    for doc in docs:
        chunk = doc["text"]
        if len(context) + len(chunk) > limit:
            break
        context += chunk + "\n\n"
    return context.strip()
