import json
import redis.asyncio as aioredis
from app.config import get_settings
from app.utils.text import stable_cache_key

_redis: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        raise RuntimeError("Redis not initialized. Call init_redis() at startup.")
    return _redis


async def init_redis() -> None:
    global _redis
    cfg = get_settings()
    _redis = aioredis.Redis(
        host=cfg.redis_host,
        port=cfg.redis_port,
        decode_responses=True,
    )
    await _redis.ping()


async def close_redis() -> None:
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None


# ─────────────────────────────────────────
# Search result cache
# ─────────────────────────────────────────

async def get_cached_search(query: str, user_id: str) -> list[dict] | None:
    r = await get_redis()
    key = stable_cache_key(f"{user_id}:{query}", prefix="rag_search")
    raw = await r.get(key)
    if raw:
        return json.loads(raw)
    return None


async def set_cached_search(query: str, user_id: str, results: list[dict]) -> None:
    r = await get_redis()
    key = stable_cache_key(f"{user_id}:{query}", prefix="rag_search")
    cfg = get_settings()
    await r.setex(key, cfg.cache_ttl_seconds, json.dumps(results))


# ─────────────────────────────────────────
# Embedding cache
# ─────────────────────────────────────────

async def get_cached_embedding(text: str) -> list[float] | None:
    r = await get_redis()
    key = stable_cache_key(text, prefix="emb")
    raw = await r.get(key)
    if raw:
        return json.loads(raw)
    return None


async def set_cached_embedding(text: str, embedding: list[float]) -> None:
    r = await get_redis()
    key = stable_cache_key(text, prefix="emb")
    await r.setex(key, 3600, json.dumps(embedding))  # 1h TTL for embeddings


# ─────────────────────────────────────────
# Rate limiting
# ─────────────────────────────────────────

async def check_rate_limit(user_id: str, plan: str) -> tuple[bool, int]:
    """
    Returns (allowed, remaining).
    Uses sliding window via Redis INCR + EXPIRE.
    """
    from datetime import date
    cfg = get_settings()

    limits = {
        "free": cfg.free_queries_per_day,
        "pro": cfg.pro_queries_per_day,
        "enterprise": cfg.enterprise_queries_per_day,
    }
    limit = limits.get(plan, cfg.free_queries_per_day)

    r = await get_redis()
    key = f"rate:{user_id}:{date.today().isoformat()}"
    count = await r.incr(key)
    if count == 1:
        await r.expire(key, 86400)  # 24h

    remaining = max(0, limit - count)
    return count <= limit, remaining
