from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.services.auth import current_user
from app.db.postgres import get_pool

router = APIRouter(prefix="/collections", tags=["collections"])


class CollectionCreate(BaseModel):
    name: str
    description: str = ""


@router.get("")
async def list_collections(user=Depends(current_user)):
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT c.id, c.name, c.description, c.created_at,
               COUNT(d.id) AS doc_count
        FROM collections c
        LEFT JOIN documents d ON d.collection_id = c.id
        WHERE c.user_id = $1
        GROUP BY c.id
        ORDER BY c.created_at DESC
        """,
        user["id"],
    )
    return [dict(r) for r in rows]


@router.post("", status_code=201)
async def create_collection(body: CollectionCreate, user=Depends(current_user)):
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO collections (user_id, name, description)
        VALUES ($1, $2, $3)
        RETURNING id, name, description, created_at
        """,
        user["id"], body.name, body.description,
    )
    return dict(row)


@router.delete("/{collection_id}", status_code=204)
async def delete_collection(collection_id: str, user=Depends(current_user)):
    pool = await get_pool()
    result = await pool.execute(
        "DELETE FROM collections WHERE id = $1 AND user_id = $2",
        collection_id, user["id"],
    )
    if result == "DELETE 0":
        raise HTTPException(404, "Collection not found")
