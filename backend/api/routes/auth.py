from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr
import jwt
import bcrypt
import os, uuid, hashlib, time
from db.database import get_db
from db.models import User

# ── In-memory user cache — eliminates one DB roundtrip per request ────────────
# Keyed by JWT token string. TTL = 60 seconds.
_user_cache: dict[str, tuple[User, float]] = {}
_USER_CACHE_TTL = 60  # seconds

router = APIRouter(prefix="/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
ALGORITHM = "HS256"


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_token(data: dict) -> str:
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Check cache first — avoids DB hit on every request
    now = time.monotonic()
    cached = _user_cache.get(token)
    if cached:
        user, cached_at = cached
        if now - cached_at < _USER_CACHE_TTL:
            return user
        del _user_cache[token]   # expired

    user = (await db.execute(select(User).where(User.id == uuid.UUID(user_id)))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    _user_cache[token] = (user, now)
    return user


def invalidate_user_cache(token: str | None = None):
    """Call after updating user fields so the cache doesn't serve stale data."""
    if token:
        _user_cache.pop(token, None)
    else:
        _user_cache.clear()


class SignupRequest(BaseModel):
    name: str
    username: str
    email: EmailStr
    password: str
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""


class SmtpSettingsRequest(BaseModel):
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


@router.post("/signup")
async def signup(req: SignupRequest, db: AsyncSession = Depends(get_db)):
    if (await db.execute(select(User).where(User.email == req.email))).scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
    if (await db.execute(select(User).where(User.username == req.username))).scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already taken")

    user = User(
        name=req.name,
        username=req.username,
        email=req.email,
        password_hash=hash_password(req.password),
        api_key_hash=hash_api_key("none"),
        smtp_host=req.smtp_host or None,
        smtp_port=req.smtp_port if req.smtp_host else None,
        smtp_user=req.smtp_user or None,
        smtp_password=req.smtp_password or None,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {
        "access_token": create_token({"sub": str(user.id)}),
        "token_type": "bearer",
        "user_id": str(user.id),
        "name": user.name,
        "username": user.username,
    }


@router.post("/login")
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.email == req.email))).scalar_one_or_none()
    if not user or not user.password_hash or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return {
        "access_token": create_token({"sub": str(user.id)}),
        "token_type": "bearer",
        "user_id": str(user.id),
        "name": user.name,
        "username": user.username,
    }


@router.get("/smtp-settings")
async def get_smtp_settings(current_user: User = Depends(get_current_user)):
    return {
        "smtp_host": current_user.smtp_host or "",
        "smtp_port": current_user.smtp_port or 587,
        "smtp_user": current_user.smtp_user or "",
        "smtp_configured": bool(current_user.smtp_host and current_user.smtp_user and current_user.smtp_password),
    }


@router.put("/smtp-settings")
async def update_smtp_settings(
    req: SmtpSettingsRequest,
    token: str = Depends(oauth2_scheme),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    clearing = not req.smtp_host  # explicit clear when host is blank

    current_user.smtp_host = req.smtp_host or None
    current_user.smtp_port = req.smtp_port if req.smtp_host else None
    current_user.smtp_user = req.smtp_user or None

    # Only overwrite the stored password when:
    #   • a new password was explicitly provided, OR
    #   • the user is clearing all settings (host blank)
    # This prevents a "save without re-entering password" from wiping it.
    if req.smtp_password:
        current_user.smtp_password = req.smtp_password
    elif clearing:
        current_user.smtp_password = None
    # else: keep the existing stored password unchanged

    db.add(current_user)
    await db.commit()
    invalidate_user_cache(token)
    return {"success": True}
