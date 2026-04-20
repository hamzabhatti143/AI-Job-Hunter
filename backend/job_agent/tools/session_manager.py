"""session_manager_tool — Maintain logged-in sessions for portal accounts.

Stores serialised browser cookies / auth tokens per portal to avoid
re-logging in each pipeline run. Prevents repeated CAPTCHA triggers.

Storage: session_tokens DB table (created automatically).
Encryption: same Fernet key as credential_vault (VAULT_SECRET env var).
"""
import json
import os
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import text
from agents import function_tool

from db.database import AsyncSessionLocal

SESSION_TTL_HOURS = int(os.getenv("SESSION_TTL_HOURS", "24"))

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS session_tokens (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    portal_name    TEXT NOT NULL,
    cookies_json   TEXT NOT NULL,
    created_at     TIMESTAMPTZ DEFAULT now(),
    expires_at     TIMESTAMPTZ NOT NULL,
    UNIQUE (user_id, portal_name)
);
"""


def _encrypt(text_data: str) -> str:
    vault_secret = os.getenv("VAULT_SECRET", "")
    if not vault_secret:
        return text_data  # No encryption if vault not configured
    try:
        from cryptography.fernet import Fernet
        return Fernet(vault_secret.encode()).encrypt(text_data.encode()).decode()
    except Exception:
        return text_data


def _decrypt(ciphertext: str) -> str:
    vault_secret = os.getenv("VAULT_SECRET", "")
    if not vault_secret:
        return ciphertext
    try:
        from cryptography.fernet import Fernet
        return Fernet(vault_secret.encode()).decrypt(ciphertext.encode()).decode()
    except Exception:
        return ciphertext


async def _ensure_table(session) -> None:
    await session.execute(text(_CREATE_SQL))


async def session_save_impl(
    user_id: str,
    portal_name: str,
    cookies: list[dict] | dict,
) -> str:
    """Store encrypted session cookies for a portal."""
    uid = uuid.UUID(user_id)
    cookies_raw   = json.dumps(cookies)
    cookies_enc   = _encrypt(cookies_raw)
    now           = datetime.now(timezone.utc)
    expires_at    = now + timedelta(hours=SESSION_TTL_HOURS)

    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await _ensure_table(session)
                await session.execute(text("""
                    INSERT INTO session_tokens (id, user_id, portal_name, cookies_json, expires_at)
                    VALUES (gen_random_uuid(), :uid, :portal, :cookies, :exp)
                    ON CONFLICT (user_id, portal_name) DO UPDATE
                        SET cookies_json = EXCLUDED.cookies_json,
                            created_at   = now(),
                            expires_at   = EXCLUDED.expires_at
                """), {"uid": uid, "portal": portal_name, "cookies": cookies_enc, "exp": expires_at})

        return json.dumps({
            "success":     True,
            "portal_name": portal_name,
            "expires_at":  expires_at.isoformat(),
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


async def session_load_impl(user_id: str, portal_name: str) -> str:
    """Retrieve stored session cookies if still valid."""
    uid = uuid.UUID(user_id)
    now = datetime.now(timezone.utc)

    try:
        async with AsyncSessionLocal() as session:
            await _ensure_table(session)
            result = await session.execute(text("""
                SELECT cookies_json, expires_at
                FROM session_tokens
                WHERE user_id = :uid AND portal_name = :portal
                LIMIT 1
            """), {"uid": uid, "portal": portal_name})
            row = result.fetchone()

        if not row:
            return json.dumps({"found": False, "reason": "no_session"})
        if row.expires_at < now:
            return json.dumps({"found": False, "reason": "expired"})

        cookies = json.loads(_decrypt(row.cookies_json))
        return json.dumps({
            "found":      True,
            "cookies":    cookies,
            "expires_at": row.expires_at.isoformat(),
        })
    except Exception as e:
        return json.dumps({"found": False, "error": str(e)})


async def session_invalidate_impl(user_id: str, portal_name: str) -> str:
    """Delete a stored session (forces re-login next run)."""
    uid = uuid.UUID(user_id)
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await _ensure_table(session)
                await session.execute(text("""
                    DELETE FROM session_tokens
                    WHERE user_id = :uid AND portal_name = :portal
                """), {"uid": uid, "portal": portal_name})
        return json.dumps({"success": True})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@function_tool
async def session_manager_save(user_id: str, portal_name: str, cookies_json: str) -> str:
    """Save browser session cookies for a portal to avoid re-login.

    cookies_json: JSON-serialised list of cookie dicts from Playwright/Selenium.
    Session expires after SESSION_TTL_HOURS (default 24 h).
    """
    cookies = json.loads(cookies_json)
    return await session_save_impl(user_id=user_id, portal_name=portal_name, cookies=cookies)


@function_tool
async def session_manager_load(user_id: str, portal_name: str) -> str:
    """Load saved session cookies for a portal.

    Returns found=True + cookies list when a valid session exists.
    Returns found=False when no session or session has expired.
    """
    return await session_load_impl(user_id=user_id, portal_name=portal_name)
