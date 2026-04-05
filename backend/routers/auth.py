"""
Single-user authentication.
Only alonzo.larraguibel@gmail.com can log in.
First visit: set a password. Subsequent visits: check it.
"""
import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from database import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])

ALLOWED_EMAIL = "alonzo.larraguibel@gmail.com"
JWT_SECRET = os.environ.get("JWT_SECRET", "daytrader-local-jwt-secret-change-in-prod")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 30

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)


def _make_token(email: str) -> str:
    payload = {
        "sub": email,
        "exp": datetime.utcnow() + timedelta(days=JWT_EXPIRE_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme)) -> str:
    """Dependency: validate Bearer JWT and return email. Raises 401 if invalid."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        email: str = payload.get("sub", "")
        if email != ALLOWED_EMAIL:
            raise HTTPException(status_code=401, detail="Invalid user")
        return email
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# ── Request models ────────────────────────────────────────────────────────────

class CheckEmailRequest(BaseModel):
    email: str


class LoginRequest(BaseModel):
    email: str
    password: str


class SetPasswordRequest(BaseModel):
    email: str
    password: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/check-email")
async def check_email(req: CheckEmailRequest, db: AsyncSession = Depends(get_db)):
    """Step 1: check if this email is allowed and whether a password has been set."""
    if req.email.strip().lower() != ALLOWED_EMAIL:
        raise HTTPException(status_code=403, detail="This email is not authorised.")

    row = await db.execute(
        text("SELECT password_hash FROM auth_users WHERE email = :email"),
        {"email": ALLOWED_EMAIL},
    )
    user = row.fetchone()
    return {"has_password": bool(user and user[0])}


@router.post("/set-password")
async def set_password(req: SetPasswordRequest, db: AsyncSession = Depends(get_db)):
    """First-time setup: set the password for the allowed email."""
    if req.email.strip().lower() != ALLOWED_EMAIL:
        raise HTTPException(status_code=403, detail="Not authorised.")
    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")

    # Only allowed if no password is set yet
    row = await db.execute(
        text("SELECT password_hash FROM auth_users WHERE email = :email"),
        {"email": ALLOWED_EMAIL},
    )
    existing = row.fetchone()
    if existing and existing[0]:
        raise HTTPException(status_code=400, detail="Password already set. Use /login.")

    hashed = pwd_ctx.hash(req.password)
    if existing:
        await db.execute(
            text("UPDATE auth_users SET password_hash = :h WHERE email = :e"),
            {"h": hashed, "e": ALLOWED_EMAIL},
        )
    else:
        await db.execute(
            text("INSERT INTO auth_users (email, password_hash) VALUES (:e, :h)"),
            {"e": ALLOWED_EMAIL, "h": hashed},
        )
    await db.commit()
    return {"token": _make_token(ALLOWED_EMAIL)}


@router.post("/login")
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Validate email + password, return JWT."""
    if req.email.strip().lower() != ALLOWED_EMAIL:
        raise HTTPException(status_code=403, detail="Not authorised.")

    row = await db.execute(
        text("SELECT password_hash FROM auth_users WHERE email = :email"),
        {"email": ALLOWED_EMAIL},
    )
    user = row.fetchone()
    if not user or not user[0]:
        raise HTTPException(status_code=400, detail="No password set yet. Please set a password first.")

    if not pwd_ctx.verify(req.password, user[0]):
        raise HTTPException(status_code=401, detail="Incorrect password.")

    return {"token": _make_token(ALLOWED_EMAIL)}


@router.get("/me")
async def me(email: str = Depends(verify_token)):
    """Validate token — returns user info if valid."""
    return {"email": email, "authenticated": True}
