from fastapi import APIRouter
from pydantic import BaseModel, EmailStr

from app.services.auth import create_user, authenticate_user, create_token

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterBody(BaseModel):
    email: EmailStr
    password: str


class LoginBody(BaseModel):
    email: EmailStr
    password: str


@router.post("/register", status_code=201)
async def register(body: RegisterBody):
    if len(body.password) < 8:
        from fastapi import HTTPException
        raise HTTPException(400, "Password must be at least 8 characters")
    user = await create_user(body.email, body.password)
    token = create_token(str(user["id"]), user["email"])
    return {"access_token": token, "token_type": "bearer", "user": {
        "id": str(user["id"]),
        "email": user["email"],
        "plan": user["plan"],
    }}


@router.post("/login")
async def login(body: LoginBody):
    user = await authenticate_user(body.email, body.password)
    token = create_token(user["id"], user["email"])
    return {"access_token": token, "token_type": "bearer", "user": user}
