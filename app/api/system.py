from fastapi import APIRouter, Depends
from app.services.auth import current_user
from app.services.llm_router import get_router
from app.db.postgres import get_pool
from app.utils.cache import get_redis

router = APIRouter(tags=["system"])


@router.get("/health")
async def health():
    """Public liveness probe."""
    return {"status": "ok"}


@router.get("/status")
async def status(user=Depends(current_user)):
    """Authenticated — returns full cluster state."""
    router_status = await get_router().get_status()

    # DB ping
    try:
        pool = await get_pool()
        await pool.fetchval("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False

    # Redis ping
    try:
        r = await get_redis()
        await r.ping()
        redis_ok = True
    except Exception:
        redis_ok = False

    return {
        "database": "ok" if db_ok else "error",
        "redis": "ok" if redis_ok else "error",
        "llm_nodes": router_status,
    }


@router.get("/me")
async def me(user=Depends(current_user)):
    """Current user info + usage stats."""
    pool = await get_pool()
    from datetime import date
    today = date.today()
    usage = await pool.fetchval(
        """
        SELECT COUNT(*) FROM usage_log
        WHERE user_id = $1
          AND action = 'query'
          AND DATE(created_at) = $2
        """,
        user["id"], today,
    )
    doc_count = await pool.fetchval(
        "SELECT COUNT(*) FROM documents WHERE user_id = $1 AND status = 'ready'",
        user["id"],
    )
    return {
        "user": user,
        "usage": {
            "queries_today": usage or 0,
            "documents": doc_count or 0,
        },
    }
