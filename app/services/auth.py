from datetime import datetime, timedelta, timezone
from typing import Optional
import uuid

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import get_settings
from app.db.postgres import get_pool

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = HTTPBearer()


def hash_password(plain: str) -> str:
    return pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_ctx.verify(plain, hashed)


def create_token(user_id: str, email: str) -> str:
    cfg = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=cfg.access_token_expire_minutes
    )
    payload = {"sub": user_id, "email": email, "exp": expire}
    return jwt.encode(payload, cfg.secret_key, algorithm=cfg.algorithm)


def decode_token(token: str) -> dict:
    cfg = get_settings()
    try:
        return jwt.decode(token, cfg.secret_key, algorithms=[cfg.algorithm])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


# ─────────────────────────────────────────
# DB helpers
# ─────────────────────────────────────────

async def create_user(email: str, password: str) -> dict:
    pool = await get_pool()
    hashed = hash_password(password)
    try:
        row = await pool.fetchrow(
            """
            INSERT INTO users (email, hashed_pw)
            VALUES ($1, $2)
            RETURNING id, email, plan, created_at
            """,
            email, hashed,
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
    return dict(row)


async def authenticate_user(email: str, password: str) -> dict:
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT id, email, hashed_pw, plan, is_active FROM users WHERE email = $1",
        email,
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    if not row["is_active"]:
        raise HTTPException(status_code=403, detail="Account disabled")
    if not verify_password(password, row["hashed_pw"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    return {"id": str(row["id"]), "email": row["email"], "plan": row["plan"]}


async def get_user_by_id(user_id: str) -> dict | None:
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT id, email, plan, is_active FROM users WHERE id = $1",
        user_id,
    )
    if not row:
        return None
    return {"id": str(row["id"]), "email": row["email"], "plan": row["plan"]}


# ─────────────────────────────────────────
# FastAPI dependency
# ─────────────────────────────────────────

async def current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
) -> dict:
    payload = decode_token(credentials.credentials)
    user = await get_user_by_id(payload["sub"])
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user
