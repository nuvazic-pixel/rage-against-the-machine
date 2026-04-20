"""
Document ingestion pipeline:
  1. Parse file (txt, md, pdf placeholder)
  2. Chunk with sentence-aware splitter
  3. Batch embed
  4. Store in PostgreSQL + update document status
"""
import asyncio
import io
from pathlib import Path

from app.config import get_settings
from app.db.postgres import insert_chunk, update_document_status, get_pool
from app.services.embedding import embed_batch_direct
from app.utils.text import chunk_text, extract_obsidian_links
import structlog

log = structlog.get_logger()


async def ingest_document(
    doc_id: str,
    collection_id: str,
    user_id: str,
    content: str,
    filename: str,
) -> None:
    """
    Full ingestion pipeline for a single document.
    Runs in background — updates document.status on completion.
    """
    cfg = get_settings()
    try:
        log.info("ingestion_start", doc_id=doc_id, filename=filename)

        # 1. Extract links (Obsidian/wiki style)
        links = extract_obsidian_links(content)

        # 2. Chunk
        chunks = chunk_text(
            content,
            max_chars=cfg.chunk_size,
            overlap_sentences=cfg.chunk_overlap_sentences,
        )

        if not chunks:
            await update_document_status(doc_id, "error", error_msg="No content extracted")
            return

        total_chars = sum(len(c) for c in chunks)

        # 3. Batch embed (all chunks at once)
        embeddings = await embed_batch_direct(chunks)

        # 4. Store all chunks
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            meta = {
                "filename": filename,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "links": links,
            }
            await insert_chunk(
                document_id=doc_id,
                collection_id=collection_id,
                user_id=user_id,
                chunk_index=i,
                text=chunk,
                embedding=embedding,
                metadata=meta,
            )

        # 5. Mark ready
        await update_document_status(
            doc_id,
            status="ready",
            chunk_count=len(chunks),
            char_count=total_chars,
        )
        log.info("ingestion_complete", doc_id=doc_id, chunks=len(chunks))

    except Exception as exc:
        log.error("ingestion_failed", doc_id=doc_id, error=str(exc))
        await update_document_status(doc_id, "error", error_msg=str(exc))


def parse_uploaded_file(filename: str, raw_bytes: bytes) -> str:
    """
    Extract text from uploaded file.
    Supports: .txt, .md, .py, .json, .csv
    PDF support requires pypdf (add to requirements if needed).
    """
    suffix = Path(filename).suffix.lower()

    if suffix in {".txt", ".md", ".py", ".js", ".ts", ".json", ".csv", ".yaml", ".yml"}:
        for enc in ("utf-8", "latin-1", "cp1252"):
            try:
                return raw_bytes.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw_bytes.decode("utf-8", errors="replace")

    if suffix == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(raw_bytes))
            return "\n\n".join(
                page.extract_text() or "" for page in reader.pages
            )
        except ImportError:
            raise ValueError("PDF support requires: pip install pypdf")

    raise ValueError(f"Unsupported file type: {suffix}")
