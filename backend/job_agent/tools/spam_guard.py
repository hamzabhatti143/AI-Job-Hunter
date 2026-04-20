"""spam_guard_tool — Enforce per-user daily email send limit.

Prevents sending too many application emails per day (default cap: 20).
Checks sent_emails table for today's count.
Returns allowed=True/False before email_sender runs.
"""
import json
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func
from db.database import AsyncSessionLocal
from db.models import SentEmail
import uuid

DAILY_LIMIT = int(__import__("os").getenv("EMAIL_DAILY_LIMIT", "20"))


async def spam_guard_impl(user_id: str) -> str:
    """Check if user has capacity to send more emails today."""
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(func.count(SentEmail.id)).where(
                    SentEmail.user_id == uuid.UUID(user_id),
                    SentEmail.sent_at >= today_start,
                )
            )
            sent_today = result.scalar() or 0

        allowed = sent_today < DAILY_LIMIT
        return json.dumps({
            "success": True,
            "allowed": allowed,
            "sent_today": sent_today,
            "limit": DAILY_LIMIT,
            "remaining": max(0, DAILY_LIMIT - sent_today),
            "message": (
                f"OK — {DAILY_LIMIT - sent_today} emails remaining today."
                if allowed
                else f"Daily limit of {DAILY_LIMIT} emails reached. Try again tomorrow."
            ),
        })
    except Exception as e:
        # Fail open — if DB check fails, allow send but log
        return json.dumps({
            "success": False,
            "allowed": True,
            "sent_today": 0,
            "limit": DAILY_LIMIT,
            "remaining": DAILY_LIMIT,
            "error": str(e),
        })
