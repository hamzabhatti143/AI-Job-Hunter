"""portal_blacklist_tool — Skip portals that consistently fail or block automation.

Logs failed portal attempts to the portal_blacklist DB table.
Portals that exceed the failure threshold are skipped on subsequent runs.
Prevents the pipeline from getting stuck on broken or bot-blocking portals.
"""
import json
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, text
from agents import function_tool

from db.database import AsyncSessionLocal

FAILURE_THRESHOLD = int(os.getenv("PORTAL_BLACKLIST_THRESHOLD", "3"))


async def _ensure_table(session) -> None:
    """Create portal_blacklist table if missing (idempotent)."""
    await session.execute(text("""
        CREATE TABLE IF NOT EXISTS portal_blacklist (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id     UUID REFERENCES users(id) ON DELETE CASCADE,
            portal_name TEXT NOT NULL,
            portal_url  TEXT,
            reason      TEXT,
            failure_count INTEGER DEFAULT 1,
            last_failed_at TIMESTAMPTZ DEFAULT now()
        );
    """))


async def portal_blacklist_add_impl(
    user_id: str,
    portal_name: str,
    portal_url: str = "",
    reason: str = "",
) -> str:
    """Record a portal failure. Auto-increments failure_count."""
    uid = uuid.UUID(user_id)
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await _ensure_table(session)
                # Try upsert: if portal already in table, increment count
                result = await session.execute(text("""
                    SELECT id, failure_count FROM portal_blacklist
                    WHERE user_id = :uid AND portal_name = :name
                    LIMIT 1
                """), {"uid": uid, "name": portal_name})
                row = result.fetchone()

                if row:
                    new_count = row.failure_count + 1
                    await session.execute(text("""
                        UPDATE portal_blacklist
                        SET failure_count = :cnt, last_failed_at = now(), reason = :reason
                        WHERE id = :rid
                    """), {"cnt": new_count, "reason": reason, "rid": row.id})
                    blacklisted = new_count >= FAILURE_THRESHOLD
                else:
                    new_count = 1
                    await session.execute(text("""
                        INSERT INTO portal_blacklist (id, user_id, portal_name, portal_url, reason)
                        VALUES (gen_random_uuid(), :uid, :name, :url, :reason)
                    """), {"uid": uid, "name": portal_name, "url": portal_url, "reason": reason})
                    blacklisted = False

        return json.dumps({
            "success":         True,
            "portal_name":     portal_name,
            "failure_count":   new_count,
            "blacklisted":     blacklisted,
            "threshold":       FAILURE_THRESHOLD,
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


async def portal_blacklist_check_impl(user_id: str, portal_name: str) -> str:
    """Check whether a portal is currently blacklisted for this user."""
    uid = uuid.UUID(user_id)
    try:
        async with AsyncSessionLocal() as session:
            await _ensure_table(session)
            result = await session.execute(text("""
                SELECT failure_count FROM portal_blacklist
                WHERE user_id = :uid AND portal_name = :name
                LIMIT 1
            """), {"uid": uid, "name": portal_name})
            row = result.fetchone()

        if not row:
            return json.dumps({"blacklisted": False, "failure_count": 0})

        return json.dumps({
            "blacklisted":   row.failure_count >= FAILURE_THRESHOLD,
            "failure_count": row.failure_count,
            "threshold":     FAILURE_THRESHOLD,
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


async def portal_blacklist_list_impl(user_id: str) -> str:
    """Return all blacklisted portals for the user."""
    uid = uuid.UUID(user_id)
    try:
        async with AsyncSessionLocal() as session:
            await _ensure_table(session)
            result = await session.execute(text("""
                SELECT portal_name, portal_url, reason, failure_count, last_failed_at
                FROM portal_blacklist
                WHERE user_id = :uid AND failure_count >= :threshold
                ORDER BY failure_count DESC
            """), {"uid": uid, "threshold": FAILURE_THRESHOLD})
            rows = result.fetchall()

        return json.dumps({
            "success": True,
            "blacklisted_portals": [
                {
                    "portal_name":   r.portal_name,
                    "portal_url":    r.portal_url or "",
                    "reason":        r.reason or "",
                    "failure_count": r.failure_count,
                    "last_failed_at": r.last_failed_at.isoformat() if r.last_failed_at else None,
                }
                for r in rows
            ],
            "threshold": FAILURE_THRESHOLD,
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


async def portal_blacklist_reset_impl(user_id: str, portal_name: str) -> str:
    """Remove a portal from the blacklist (e.g. after fixing credentials)."""
    uid = uuid.UUID(user_id)
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await _ensure_table(session)
                await session.execute(text("""
                    DELETE FROM portal_blacklist
                    WHERE user_id = :uid AND portal_name = :name
                """), {"uid": uid, "name": portal_name})
        return json.dumps({"success": True, "portal_name": portal_name})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@function_tool
async def portal_blacklist_tool(
    user_id: str,
    portal_name: str,
    portal_url: str = "",
    reason: str = "",
) -> str:
    """Log a portal failure and auto-blacklist after threshold failures.

    Call this whenever a portal apply attempt fails. Returns blacklisted=True
    when failure_count reaches PORTAL_BLACKLIST_THRESHOLD (default 3).
    """
    return await portal_blacklist_add_impl(
        user_id=user_id, portal_name=portal_name,
        portal_url=portal_url, reason=reason,
    )
