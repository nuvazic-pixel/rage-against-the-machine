import asyncio
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form

from app.services.auth import current_user
from app.services.ingestion import ingest_document, parse_uploaded_file
from app.db.postgres import get_pool

router = APIRouter(prefix="/documents", tags=["documents"])

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


@router.get("")
async def list_documents(
    collection_id: str | None = None,
    user=Depends(current_user),
):
    pool = await get_pool()
    if collection_id:
        rows = await pool.fetch(
            """
            SELECT id, collection_id, filename, file_type,
                   char_count, chunk_count, status, error_msg, created_at
            FROM documents
            WHERE user_id = $1 AND collection_id = $2
            ORDER BY created_at DESC
            """,
            user["id"], collection_id,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT id, collection_id, filename, file_type,
                   char_count, chunk_count, status, error_msg, created_at
            FROM documents
            WHERE user_id = $1
            ORDER BY created_at DESC
            """,
            user["id"],
        )
    return [dict(r) for r in rows]


@router.post("", status_code=202)
async def upload_document(
    collection_id: str = Form(...),
    file: UploadFile = File(...),
    user=Depends(current_user),
):
    # Validate collection ownership
    pool = await get_pool()
    col = await pool.fetchrow(
        "SELECT id FROM collections WHERE id = $1 AND user_id = $2",
        collection_id, user["id"],
    )
    if not col:
        raise HTTPException(404, "Collection not found")

    # Size check
    raw = await file.read()
    if len(raw) > MAX_FILE_SIZE:
        raise HTTPException(413, f"File too large (max {MAX_FILE_SIZE // 1024 // 1024} MB)")

    # Parse
    try:
        content = parse_uploaded_file(file.filename, raw)
    except ValueError as exc:
        raise HTTPException(422, str(exc))

    if not content.strip():
        raise HTTPException(422, "File appears to be empty")

    # Create document record
    suffix = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "txt"
    row = await pool.fetchrow(
        """
        INSERT INTO documents (collection_id, user_id, filename, file_type, status)
        VALUES ($1, $2, $3, $4, 'processing')
        RETURNING id
        """,
        collection_id, user["id"], file.filename, suffix,
    )
    doc_id = str(row["id"])

    # Kick off background ingestion
    asyncio.create_task(
        ingest_document(
            doc_id=doc_id,
            collection_id=collection_id,
            user_id=user["id"],
            content=content,
            filename=file.filename,
        )
    )

    return {"doc_id": doc_id, "status": "processing", "filename": file.filename}


@router.get("/{doc_id}")
async def get_document(doc_id: str, user=Depends(current_user)):
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        SELECT id, collection_id, filename, file_type,
               char_count, chunk_count, status, error_msg, created_at
        FROM documents
        WHERE id = $1 AND user_id = $2
        """,
        doc_id, user["id"],
    )
    if not row:
        raise HTTPException(404, "Document not found")
    return dict(row)


@router.delete("/{doc_id}", status_code=204)
async def delete_document(doc_id: str, user=Depends(current_user)):
    pool = await get_pool()
    result = await pool.execute(
        "DELETE FROM documents WHERE id = $1 AND user_id = $2",
        doc_id, user["id"],
    )
    if result == "DELETE 0":
        raise HTTPException(404, "Document not found")
