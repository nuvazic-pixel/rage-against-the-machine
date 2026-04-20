import asyncio
from sentence_transformers import CrossEncoder
from app.utils.batching import AsyncBatcher
import structlog

log = structlog.get_logger()

_model: CrossEncoder | None = None
_batcher: AsyncBatcher | None = None
_semaphore = asyncio.Semaphore(2)


def get_reranker() -> CrossEncoder:
    global _model
    if _model is None:
        log.info("loading_reranker_model")
        _model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    return _model


async def _rerank_batch(
    batch: list[tuple[str, list[dict]]]
) -> list[list[float]]:
    async with _semaphore:
        model = get_reranker()

        def run() -> list[list[float]]:
            outputs = []
            for query, docs in batch:
                pairs = [(query, d["text"]) for d in docs]
                scores = model.predict(pairs).tolist()
                outputs.append(scores)
            return outputs

        return await asyncio.to_thread(run)


def get_batcher() -> AsyncBatcher:
    global _batcher
    if _batcher is None:
        _batcher = AsyncBatcher(
            handler=_rerank_batch,
            max_batch_size=8,
            max_wait_ms=10,
            name="reranker",
        )
    return _batcher


async def rerank_docs(query: str, docs: list[dict]) -> list[dict]:
    """Rerank docs using CrossEncoder. Returns docs sorted by score desc."""
    if not docs:
        return docs

    batcher = get_batcher()
    scores: list[float] = await batcher.submit((query, docs))

    for doc, score in zip(docs, scores):
        doc["cross_score"] = float(score)

    return sorted(docs, key=lambda d: d["cross_score"], reverse=True)
