# EAON evidence boundary v1

The root application is the canonical entrypoint. The existing `rag-saas/`
copy is retained for compatibility; tests keep the changed boundary files equal.
No stores or deployments are migrated.

`GET /chat/evidence?q=...&collection_id=...` uses the existing bearer JWT.
The server checks the active user, collection ownership and retrieval budget
before retrieval. It bypasses the search-result cache and never calls answer
generation. Embedding and reranking still use the configured local services.

Response contract:

```json
{
  "schema_version": "eaon.evidence.v1",
  "query": "local evidence",
  "owner_id": "authenticated-user-id",
  "collection_id": "requested-owned-collection-id",
  "retrieved_at": "2026-10-30T12:00:00+00:00",
  "cache": "bypassed",
  "authority": "candidate_only",
  "results": [{"chunk_id": "1", "document_id": "document-id",
    "text": "Captured source fragment", "sha256": "SHA256_OF_UTF8_TEXT", "score": 0.8}]
}
```

An empty result is absence of evidence. Score is ranking metadata, not truth
confidence or permission to run a tool. The digest identifies the captured
fragment, not the original whole file or independent truth. Fresh retrieval
does not invalidate historical source snapshots already stored by a caller.

The regular chat search cache now separates user, collection and exact query.
It retains its configured TTL; EAON uses the uncached evidence route so deleted
documents are not resurrected from that result cache. Corpus mutation during a
request is not a transactionally pinned corpus snapshot.

Production auth rejects the shipped default/short signing key, and disabled
users cannot reuse an unexpired token. Configure a unique strong `SECRET_KEY`.
The existing JWT is an account token, not a newly introduced read-only credential;
the EAON client limits itself to this GET route.

Contract tests use signed synthetic tokens/fake infrastructure. They cover
ownership denial before retrieval, quota denial, exact cache scope, digest
generation, PostgreSQL JSON metadata decoding and mirrored entrypoint files.
They do not validate model quality, container deployment, real DB migrations,
or production operations. No model weights are installed by this suite.

```sh
python -m pip install -r requirements-contract-tests.txt
python -m pytest tests -q
```

The separate CI `native-retrieval` job uses disposable PostgreSQL 16/pgvector
and Redis 7 containers. `scripts/probe_native_retrieval.py` exercises native
UUID/vector/JSON bindings, signed JWT authentication, owner/collection checks,
rate limits and fresh evidence after deleting a fixture document. Only the
384-dimensional embedding and reranker are deterministic fixtures. This probe
requires an empty local `synapse_contract` database and an explicit
`SYNAPSE_DISPOSABLE_CONTRACT=1`; it never loads a local `.env`. It is not a
model-quality or deployment test.

Driver encoding follows [asyncpg's type conversion contract](https://magicstack.github.io/asyncpg/current/usage.html#type-conversion):
UUID objects for UUID parameters, JSON strings for JSONB and finite text
vectors where a custom pgvector codec has not been registered.
