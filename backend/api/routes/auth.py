from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr
from urllib.parse import urlencode
from datetime import datetime, timezone, timedelta
import jwt
import bcrypt
import httpx
import secrets
import os, uuid, hashlib, time
from db.database import get_db
from db.models import User

# ── In-memory user cache — eliminates one DB roundtrip per request ────────────
_user_cache: dict[str, tuple[User, float]] = {}
_USER_CACHE_TTL = 60  # seconds

# ── In-memory OAuth state store — short-lived, expires in 10 min ─────────────
_pending_oauth: dict[str, tuple[str, float]] = {}  # state → (user_id, expires_at)

router = APIRouter(prefix="/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
ALGORITHM = "HS256"

GOOGLE_AUTH_URL  = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_SCOPES     = "https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.readonly"


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

    now = time.monotonic()
    cached = _user_cache.get(token)
    if cached:
        user, cached_at = cached
        if now - cached_at < _USER_CACHE_TTL:
            return await db.merge(user)
        del _user_cache[token]

    user = (await db.execute(select(User).where(User.id == uuid.UUID(user_id)))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    _user_cache[token] = (user, now)
    return user


def invalidate_user_cache(token: str | None = None):
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


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return {
        "name": current_user.name,
        "email": current_user.email,
        "username": current_user.username,
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
    clearing = not req.smtp_host

    current_user.smtp_host = req.smtp_host or None
    current_user.smtp_port = req.smtp_port if req.smtp_host else None
    current_user.smtp_user = req.smtp_user or None

    if req.smtp_password:
        current_user.smtp_password = req.smtp_password
    elif clearing:
        current_user.smtp_password = None

    db.add(current_user)
    await db.commit()
    invalidate_user_cache(token)
    return {"success": True}


# ── Gmail OAuth ───────────────────────────────────────────────────────────────

class GmailCredentialsRequest(BaseModel):
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str


@router.post("/gmail/credentials")
async def save_gmail_credentials(
    req: GmailCredentialsRequest,
    token: str = Depends(oauth2_scheme),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save the user's own Google OAuth client credentials."""
    if not req.google_client_id.strip() or not req.google_client_secret.strip():
        raise HTTPException(status_code=400, detail="Client ID and Client Secret are required.")
    if not req.google_redirect_uri.strip():
        raise HTTPException(status_code=400, detail="Redirect URI is required.")
    current_user.google_client_id     = req.google_client_id.strip()
    current_user.google_client_secret = req.google_client_secret.strip()
    current_user.google_redirect_uri  = req.google_redirect_uri.strip()
    db.add(current_user)
    await db.commit()
    invalidate_user_cache(token)
    return {"success": True}


@router.get("/gmail/connect")
async def gmail_connect(request: Request, current_user: User = Depends(get_current_user)):
    client_id     = current_user.google_client_id     or os.getenv("GOOGLE_CLIENT_ID", "")
    client_secret = current_user.google_client_secret or os.getenv("GOOGLE_CLIENT_SECRET", "")
    redirect_uri  = current_user.google_redirect_uri  or os.getenv("GOOGLE_REDIRECT_URI", "")

    if not client_id or not client_secret:
        raise HTTPException(
            status_code=400,
            detail="Google Client ID and Client Secret are required. Enter them first."
        )
    if not redirect_uri:
        raise HTTPException(
            status_code=400,
            detail="Redirect URI is required. Enter it first."
        )

    # redirect_uri is now always from user input or env var — no auto-derivation

    state = secrets.token_urlsafe(16)
    _pending_oauth[state] = (str(current_user.id), time.monotonic() + 600, client_id, client_secret, redirect_uri)

    url = GOOGLE_AUTH_URL + "?" + urlencode({
        "client_id":     client_id,
        "redirect_uri":  redirect_uri,
        "response_type": "code",
        "scope":         GMAIL_SCOPES,
        "access_type":   "offline",
        "prompt":        "consent",
        "state":         state,
    })
    return {"url": url}


@router.get("/gmail/callback")
async def gmail_callback(
    code: str = None,
    state: str = None,
    error: str = None,
    db: AsyncSession = Depends(get_db),
):
    frontend = os.getenv("FRONTEND_URL", "http://localhost:3000")

    if error or not code or not state:
        return RedirectResponse(f"{frontend}/dashboard/settings?gmail=error")

    entry = _pending_oauth.pop(state, None)
    if not entry:
        return RedirectResponse(f"{frontend}/dashboard/settings?gmail=error")

    user_id, expires_at, client_id, client_secret, redirect_uri = entry
    if time.monotonic() > expires_at:
        return RedirectResponse(f"{frontend}/dashboard/settings?gmail=expired")

    async with httpx.AsyncClient() as client:
        r = await client.post(GOOGLE_TOKEN_URL, data={
            "code":          code,
            "client_id":     client_id,
            "client_secret": client_secret,
            "redirect_uri":  redirect_uri,
            "grant_type":    "authorization_code",
        })
        if r.status_code != 200:
            return RedirectResponse(f"{frontend}/dashboard/settings?gmail=error")
        tokens = r.json()

    user = (await db.execute(select(User).where(User.id == uuid.UUID(user_id)))).scalar_one_or_none()
    if not user:
        return RedirectResponse(f"{frontend}/dashboard/settings?gmail=error")

    user.gmail_access_token  = tokens.get("access_token")
    user.gmail_token_expiry  = datetime.now(timezone.utc) + timedelta(seconds=tokens.get("expires_in", 3600))
    if tokens.get("refresh_token"):
        user.gmail_refresh_token = tokens["refresh_token"]
    db.add(user)
    await db.commit()
    invalidate_user_cache()

    return RedirectResponse(f"{frontend}/dashboard/settings?gmail=connected")


@router.get("/gmail/status")
async def gmail_status(current_user: User = Depends(get_current_user)):
    return {
        "connected": bool(current_user.gmail_access_token and current_user.gmail_refresh_token),
        "email":     current_user.email,
    }


@router.delete("/gmail/disconnect")
async def gmail_disconnect(
    token: str = Depends(oauth2_scheme),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    current_user.gmail_access_token  = None
    current_user.gmail_refresh_token = None
    current_user.gmail_token_expiry  = None
    db.add(current_user)
    await db.commit()
    invalidate_user_cache(token)
    return {"success": True}
