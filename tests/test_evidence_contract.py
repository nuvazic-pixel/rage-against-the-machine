import asyncio
from hashlib import sha256
from types import ModuleType, SimpleNamespace
import sys
from pathlib import Path
import json
from uuid import UUID
from unittest.mock import AsyncMock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

from app.api import evidence
from app.services import auth, retrieval
from app.utils import cache
from app.db import postgres


@pytest.fixture
def endpoint(monkeypatch):
    app = FastAPI()
    app.include_router(evidence.router)
    user = {"id": '11111111-1111-4111-8111-111111111111', "plan": "free"}
    app.dependency_overrides[auth.current_user] = lambda: user
    pool = SimpleNamespace(fetchrow=AsyncMock(return_value={"id": 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'}))
    fetch = AsyncMock(return_value=[{"id": 7, "document_id": "doc-a", "text": "Synthetic local evidence", "cross_score": 0.8}])
    monkeypatch.setattr(evidence, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(evidence, "retrieve_fresh", fetch)
    monkeypatch.setattr(evidence, "check_rate_limit", AsyncMock(return_value=(True, 19)))
    with TestClient(app) as client:
        yield client, pool, fetch


def test_evidence_is_scoped_hashed_candidate_only(endpoint):
    client, pool, fetch = endpoint
    response = client.get("/chat/evidence", params={"q": "local", "collection_id": 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'})
    assert response.status_code == 200
    body = response.json()
    assert body["owner_id"] == '11111111-1111-4111-8111-111111111111' and body["collection_id"] == 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
    assert body["cache"] == "bypassed" and body["authority"] == "candidate_only"
    assert body["results"][0]["sha256"] == sha256(b"Synthetic local evidence").hexdigest()
    assert "answer" not in body
    assert tuple(map(str, pool.fetchrow.await_args.args[1:])) == ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', '11111111-1111-4111-8111-111111111111')
    fetch.assert_awaited_once_with("local", '11111111-1111-4111-8111-111111111111', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa')


def test_other_collection_is_denied_before_embedding_or_retrieval(endpoint):
    client, pool, fetch = endpoint
    pool.fetchrow.return_value = None
    response = client.get("/chat/evidence", params={"q": "local", "collection_id": 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'})
    assert response.status_code == 404
    fetch.assert_not_awaited()


def test_retrieval_budget_is_checked_before_embedding(endpoint, monkeypatch):
    client, _, fetch = endpoint
    monkeypatch.setattr(evidence, "check_rate_limit", AsyncMock(return_value=(False, 0)))
    assert client.get("/chat/evidence", params={"q": "local", "collection_id": 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'}).status_code == 429
    fetch.assert_not_awaited()


@pytest.mark.parametrize("params", [{"q": "local"}, {"q": "", "collection_id": "a"}, {"q": "   ", "collection_id": "a"}, {"q": "local", "collection_id": "not-a-uuid"}])
def test_implicit_or_empty_scope_rejected(endpoint, params):
    client, _, fetch = endpoint
    assert client.get("/chat/evidence", params=params).status_code == 422
    fetch.assert_not_awaited()


def test_auth_required_without_dependency_override():
    app = FastAPI()
    app.include_router(evidence.router)
    with TestClient(app) as client:
        assert client.get("/chat/evidence", params={"q": "local", "collection_id": "a"}).status_code in (401, 403)


def test_raw_route_requests_fresh_retrieval(monkeypatch):
    fetch = AsyncMock(return_value=[])
    monkeypatch.setattr(retrieval, "retrieve", fetch)
    assert asyncio.run(evidence.retrieve_fresh("q", '11111111-1111-4111-8111-111111111111', "a")) == []
    fetch.assert_awaited_once_with(query="q", user_id='11111111-1111-4111-8111-111111111111', collection_id="a", use_cache=False)


def test_fresh_pipeline_never_reads_or_writes_search_cache(monkeypatch):
    embed = ModuleType("app.services.embedding")
    embed.embed_text = AsyncMock(return_value=[0.1, 0.2])
    reranker = ModuleType("app.services.reranker")
    async def keep(query, docs): return docs
    reranker.rerank_docs = keep
    monkeypatch.setitem(sys.modules, embed.__name__, embed)
    monkeypatch.setitem(sys.modules, reranker.__name__, reranker)
    monkeypatch.setattr(retrieval, "get_settings", lambda: SimpleNamespace(vector_top_k=50, vector_weight=0.7, bm25_weight=0.3, rerank_top_n=5, final_top_k=3))
    vector = AsyncMock(return_value=[{"id": 1, "text": "local evidence", "document_id": "d", "distance": 0.2}])
    monkeypatch.setattr(retrieval, "vector_search", vector)
    monkeypatch.setattr(retrieval, "get_collection_chunks_for_bm25", AsyncMock(return_value=[{"id": 1, "text": "local evidence"}]))
    get_cache, set_cache = AsyncMock(), AsyncMock()
    monkeypatch.setattr(retrieval, "get_cached_search", get_cache)
    monkeypatch.setattr(retrieval, "set_cached_search", set_cache)
    result = asyncio.run(retrieval.retrieve("local", '11111111-1111-4111-8111-111111111111', "a", use_cache=False))
    assert result[0]["id"] == 1
    get_cache.assert_not_awaited()
    set_cache.assert_not_awaited()
    assert vector.await_args.kwargs["collection_id"] == "a"


def test_cache_identity_includes_owner_collection_and_exact_query(monkeypatch):
    class Redis:
        def __init__(self): self.values = {}
        async def get(self, key): return self.values.get(key)
        async def setex(self, key, ttl, value): self.values[key] = value
    redis = Redis()
    monkeypatch.setattr(cache, "get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr(cache, "get_settings", lambda: SimpleNamespace(cache_ttl_seconds=300))
    async def probe():
        await cache.set_cached_search("a-b", '11111111-1111-4111-8111-111111111111', [{"id": 1}], "one")
        assert await cache.get_cached_search("a-b", '11111111-1111-4111-8111-111111111111', "one") == [{"id": 1}]
        assert await cache.get_cached_search("a-b", '11111111-1111-4111-8111-111111111111', "two") is None
        assert await cache.get_cached_search("a-b", '22222222-2222-4222-8222-222222222222', "one") is None
        assert await cache.get_cached_search("a b", '11111111-1111-4111-8111-111111111111', "one") is None
    asyncio.run(probe())


def test_disabled_user_is_rejected_even_with_unexpired_token(monkeypatch):
    pool = SimpleNamespace(fetchrow=AsyncMock(return_value={"id": '11111111-1111-4111-8111-111111111111', "email": "synthetic@example.invalid", "plan": "free", "is_active": False}))
    monkeypatch.setattr(auth, "get_pool", AsyncMock(return_value=pool))
    assert asyncio.run(auth.get_user_by_id('11111111-1111-4111-8111-111111111111')) is None


def test_production_auth_rejects_shipped_default_key(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: SimpleNamespace(environment="production", secret_key="change-me-in-production-32chars!!"))
    with pytest.raises(HTTPException) as exc:
        auth.create_token('11111111-1111-4111-8111-111111111111', "synthetic@example.invalid")
    assert exc.value.status_code == 503


def test_signed_token_verification_and_wrong_signature(monkeypatch):
    cfg = SimpleNamespace(environment="testing", secret_key="synthetic-test-signing-key-for-fixtures", algorithm="HS256", access_token_expire_minutes=1)
    monkeypatch.setattr(auth, "get_settings", lambda: cfg)
    token = auth.create_token('11111111-1111-4111-8111-111111111111', "synthetic@example.invalid")
    assert auth.decode_token(token)["sub"] == '11111111-1111-4111-8111-111111111111'
    cfg.secret_key = "different-synthetic-test-key"
    with pytest.raises(HTTPException):
        auth.decode_token(token)


def test_both_existing_entrypoint_trees_share_the_retrieval_boundary():
    root = Path(__file__).resolve().parents[1]
    for rel in ("app/api/evidence.py", "app/utils/cache.py", "app/services/retrieval.py", "app/services/auth.py", "app/main.py", "app/db/postgres.py"):
        assert (root / rel).read_bytes() == (root / "rag-saas" / rel).read_bytes()


@pytest.mark.parametrize("metadata", ['{"filename":"synthetic.txt"}', {"filename": "synthetic.txt"}, None])
def test_postgres_json_metadata_and_tenant_predicates(monkeypatch, metadata):
    pool = SimpleNamespace(fetch=AsyncMock(return_value=[{"id": 1, "text": "evidence", "metadata": metadata, "document_id": "d", "distance": 0.1}]))
    monkeypatch.setattr(postgres, "get_pool", AsyncMock(return_value=pool))
    result = asyncio.run(postgres.vector_search([0.1], '11111111-1111-4111-8111-111111111111', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'))
    assert result[0]["metadata"] == ({"filename": "synthetic.txt"} if metadata is not None else {})
    sql, embedding, owner, collection, _ = pool.fetch.await_args.args
    assert isinstance(embedding, str) and json.loads(embedding) == [0.1]
    assert "user_id = $2 AND collection_id = $3" in sql
    assert (str(owner), str(collection)) == ('11111111-1111-4111-8111-111111111111', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa')


def test_chunk_insert_binds_vector_and_json_text_without_custom_codecs(monkeypatch):
    pool = SimpleNamespace(execute=AsyncMock())
    monkeypatch.setattr(postgres, "get_pool", AsyncMock(return_value=pool))
    key = "11111111-1111-4111-8111-111111111111"
    asyncio.run(postgres.insert_chunk(key, key, key, 0, "text", [0.1, 0.2], {"filename": "synthetic.txt"}))
    args = pool.execute.await_args.args
    assert all(isinstance(value, UUID) for value in args[1:4])
    assert json.loads(args[-2]) == [0.1, 0.2]
    assert json.loads(args[-1]) == {"filename": "synthetic.txt"}


@pytest.mark.parametrize("values", [[], [True], [float("nan")], [float("inf")]])
def test_invalid_vector_values_are_rejected(values):
    with pytest.raises(ValueError):
        postgres.vector_literal(values)
