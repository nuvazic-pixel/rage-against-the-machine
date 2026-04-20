import asyncio
from sentence_transformers import SentenceTransformer
from app.utils.batching import AsyncBatcher
from app.utils.cache import get_cached_embedding, set_cached_embedding
from app.config import get_settings
import structlog

log = structlog.get_logger()

_model: SentenceTransformer | None = None
_batcher: AsyncBatcher | None = None
_semaphore = asyncio.Semaphore(4)


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        cfg = get_settings()
        log.info("loading_embedding_model", model=cfg.embedding_model)
        _model = SentenceTransformer(cfg.embedding_model)
    return _model


async def _embed_batch(texts: list[str]) -> list[list[float]]:
    async with _semaphore:
        model = get_model()
        result = await asyncio.to_thread(
            lambda: model.encode(texts, normalize_embeddings=True, show_progress_bar=False).tolist()
        )
        return result


def get_batcher() -> AsyncBatcher:
    global _batcher
    if _batcher is None:
        _batcher = AsyncBatcher(
            handler=_embed_batch,
            max_batch_size=32,
            max_wait_ms=8,
            name="embedding",
        )
    return _batcher


async def embed_text(text: str) -> list[float]:
    """Embed single text with Redis caching."""
    cached = await get_cached_embedding(text)
    if cached is not None:
        return cached

    batcher = get_batcher()
    embedding = await batcher.submit(text)
    await set_cached_embedding(text, embedding)
    return embedding


async def embed_batch_direct(texts: list[str]) -> list[list[float]]:
    """Embed a batch directly — used during ingestion."""
    return await _embed_batch(texts)
