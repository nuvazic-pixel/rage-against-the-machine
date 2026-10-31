"""Exercise the actual DB/cache/auth/evidence boundary on disposable CI services.

Requires an empty local database named synapse_contract and an explicit opt-in.
Only embedding/reranking models are replaced by deterministic 384-D fixtures.
No live LLM, model weights, deployment settings or user .env files are loaded.
"""
import asyncio
from datetime import date
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import types
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def main():
    if os.environ.get("SYNAPSE_DISPOSABLE_CONTRACT") != "1":
        raise SystemExit("Set SYNAPSE_DISPOSABLE_CONTRACT=1 only for disposable local CI services")

    import httpx
    from fastapi import FastAPI
    from app.config import Settings
    from app.db import postgres
    from app.utils import cache
    from app.services import auth

    cfg = Settings(_env_file=None, db_host="127.0.0.1", db_name="synapse_contract",
                   db_user="synapse_contract", db_password="ci-disposable-only",
                   db_port=int(os.environ.get("CONTRACT_POSTGRES_PORT", "5432")),
                   redis_host="127.0.0.1", redis_port=int(os.environ.get("CONTRACT_REDIS_PORT", "6379")),
                   environment="production", secret_key="ci-synthetic-key-never-for-deployment-2026")
    # Dependency configuration is explicit; never consult a local .env.
    postgres.get_settings = cache.get_settings = auth.get_settings = lambda: cfg

    async def embed_text(_text):
        return [1.0] + [0.0] * 383

    async def rerank_docs(_query, docs):
        return [dict(doc, cross_score=1.0) for doc in docs]

    for name, function in (("embedding", embed_text), ("reranker", rerank_docs)):
        module = types.ModuleType("app.services." + name)
        setattr(module, function.__name__, function)
        sys.modules[module.__name__] = module
    from app.services import retrieval
    from app.api import evidence
    retrieval.get_settings = lambda: cfg
    await postgres.init_db()
    try:
        pool = await postgres.get_pool()
        table_count = await pool.fetchval(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")
        if table_count:
            raise RuntimeError("Refusing fixture setup: disposable contract database is not empty")
        await pool.execute((ROOT / "scripts/init.sql").read_text(encoding="utf-8"))
        await cache.init_redis()
        try:
            alice, bob, ca, cb, da, db = (uuid4() for _ in range(6))
            for uid, email in ((alice, "alice@example.invalid"), (bob, "bob@example.invalid")):
                await pool.execute("INSERT INTO users(id,email,hashed_pw) VALUES($1,$2,$3)", uid, email, "fixture")
            for cid, uid in ((ca, alice), (cb, bob)):
                await pool.execute("INSERT INTO collections(id,user_id,name) VALUES($1,$2,$3)", cid, uid, "fixture")
            for did, cid, uid in ((da, ca, alice), (db, cb, bob)):
                await pool.execute("INSERT INTO documents(id,collection_id,user_id,filename,file_type) VALUES($1,$2,$3,$4,$5)",
                                   did, cid, uid, "fixture.txt", "txt")
            for did, cid, uid, body in ((da, ca, alice, "alpha contract evidence"), (db, cb, bob, "beta private evidence")):
                await postgres.insert_chunk(str(did), str(cid), str(uid), 0, body,
                                            await embed_text(body), {"fixture": True})
            await postgres.update_document_status(str(da), "ready", 1, 23)
            assert await pool.fetchval("SELECT status FROM documents WHERE id=$1", da) == "ready"
            native = await postgres.vector_search(await embed_text("alpha"), str(alice), str(ca))
            assert len(native) == 1 and native[0]["metadata"] == {"fixture": True}
            assert native[0]["document_id"] == str(da)
            assert len(await postgres.get_collection_chunks_for_bm25(str(alice), str(ca))) == 1
            cached = await retrieval.retrieve("alpha", str(alice), str(ca))
            assert len(cached) == 1
            assert await cache.get_cached_search("alpha", str(alice), str(cb)) is None
            assert await cache.get_cached_search("alpha!", str(alice), str(ca)) is None

            app = FastAPI()
            app.include_router(evidence.router)
            token = auth.create_token(str(alice), "alice@example.invalid")
            headers = {"Authorization": "Bearer " + token}
            params = {"q": "alpha", "collection_id": str(ca)}
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://contract") as client:
                response = await client.get("/chat/evidence", params=params, headers=headers)
                assert response.status_code == 200, response.text
                data = response.json()
                assert data["cache"] == "bypassed" and data["authority"] == "candidate_only"
                assert data["owner_id"] == str(alice) and data["collection_id"] == str(ca)
                assert len(data["results"]) == 1
                result = data["results"][0]
                assert result["document_id"] == str(da)
                assert result["sha256"] == sha256(result["text"].encode()).hexdigest()
                assert (await client.get("/chat/evidence", params={**params, "collection_id": str(cb)}, headers=headers)).status_code == 404
                bob_headers = {"Authorization": "Bearer " + auth.create_token(str(bob), "bob@example.invalid")}
                assert (await client.get("/chat/evidence", params=params, headers=bob_headers)).status_code == 404
                assert (await client.get("/chat/evidence", params=params)).status_code == 403
                assert (await client.get("/chat/evidence", params=params, headers={"Authorization": "Bearer invalid"})).status_code == 401
                assert (await client.get("/chat/evidence", params={**params, "collection_id": "invalid"}, headers=headers)).status_code == 422
                # Delete only this probe's fixture: cached chat stays stale; evidence must be fresh.
                await pool.execute("DELETE FROM documents WHERE id=$1", da)
                assert len(await retrieval.retrieve("alpha", str(alice), str(ca))) == 1
                fresh = await client.get("/chat/evidence", params=params, headers=headers)
                assert fresh.status_code == 200 and fresh.json()["results"] == []
                redis = await cache.get_redis()
                await redis.set(f"rate:{alice}:{date.today().isoformat()}", cfg.free_queries_per_day)
                assert (await client.get("/chat/evidence", params=params, headers=headers)).status_code == 429
                await pool.execute("UPDATE users SET is_active=FALSE WHERE id=$1", alice)
                assert (await client.get("/chat/evidence", params=params, headers=headers)).status_code == 401
            print(json.dumps({"ok": True, "infrastructure": "native PostgreSQL/pgvector + Redis",
                              "auth": "signed synthetic JWT", "models": "deterministic 384-D fixtures",
                              "checks": ["native vector/JSON/UUID binding", "owner and collection isolation",
                                         "exact scoped cache", "fresh evidence after document deletion",
                                         "rate budget", "disabled account", "snapshot hash"]}))
        finally:
            await cache.close_redis()
    finally:
        await postgres.close_db()


if __name__ == "__main__":
    asyncio.run(main())
