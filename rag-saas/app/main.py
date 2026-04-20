import asyncio
import structlog
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.config import get_settings
from app.db.postgres import init_db, close_db
from app.utils.cache import init_redis, close_redis
from app.services.embedding import get_batcher as get_emb_batcher, get_model
from app.services.reranker import get_batcher as get_rerank_batcher, get_reranker
from app.api import auth, collections, documents, chat, system

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = get_settings()
    log.info("startup", environment=cfg.environment)

    # Init infrastructure
    await init_db()
    await init_redis()

    # Pre-load models (avoid cold-start on first request)
    log.info("preloading_models")
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, get_model)
    await loop.run_in_executor(None, get_reranker)

    # Start batchers
    get_emb_batcher().start()
    get_rerank_batcher().start()

    log.info("startup_complete")
    yield

    # Graceful shutdown
    log.info("shutdown")
    await get_emb_batcher().stop()
    await get_rerank_batcher().stop()
    await close_db()
    await close_redis()


def create_app() -> FastAPI:
    cfg = get_settings()

    app = FastAPI(
        title="RAG SaaS API",
        version="1.0.0",
        docs_url="/docs" if cfg.environment != "production" else None,
        redoc_url=None,
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Prometheus metrics
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")

    # Routers
    app.include_router(system.router)
    app.include_router(auth.router)
    app.include_router(collections.router)
    app.include_router(documents.router)
    app.include_router(chat.router)

    return app


app = create_app()
