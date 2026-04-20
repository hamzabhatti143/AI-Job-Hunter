"""notification_tool — Push real-time key-event notifications to the user.

Writes notifications to the notifications DB table.
The dashboard polls this endpoint to display in-app alerts.

Event types:
  - new_jobs_found       → new job matches from pipeline run
  - draft_ready          → application draft waiting for approval
  - email_sent           → application email was sent
  - recruiter_replied    → recruiter replied to an application
  - followup_due         → follow-up email is due
"""
import json
import uuid
from datetime import datetime, timezone
from sqlalchemy import text, select
from agents import function_tool
from db.database import AsyncSessionLocal

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS notifications (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    message    TEXT NOT NULL,
    is_read    BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);
"""


async def _ensure_table(session) -> None:
    await session.execute(text(_CREATE_SQL))


async def notification_push_impl(
    user_id: str,
    event_type: str,
    message: str,
) -> str:
    """Insert a notification record."""
    uid = uuid.UUID(user_id)
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await _ensure_table(session)
                await session.execute(text("""
                    INSERT INTO notifications (id, user_id, event_type, message)
                    VALUES (gen_random_uuid(), :uid, :evt, :msg)
                """), {"uid": uid, "evt": event_type, "msg": message})
        return json.dumps({"success": True, "event_type": event_type})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


async def notification_list_impl(user_id: str, unread_only: bool = True) -> str:
    """Fetch notifications for the user."""
    uid = uuid.UUID(user_id)
    try:
        async with AsyncSessionLocal() as session:
            await _ensure_table(session)
            filter_clause = "AND is_read = false" if unread_only else ""
            result = await session.execute(text(f"""
                SELECT id, event_type, message, is_read, created_at
                FROM notifications
                WHERE user_id = :uid {filter_clause}
                ORDER BY created_at DESC
                LIMIT 50
            """), {"uid": uid})
            rows = result.fetchall()

        return json.dumps({
            "success": True,
            "notifications": [
                {
                    "id":         str(r.id),
                    "event_type": r.event_type,
                    "message":    r.message,
                    "is_read":    r.is_read,
                    "created_at": r.created_at.isoformat(),
                }
                for r in rows
            ],
            "count": len(rows),
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


async def notification_mark_read_impl(user_id: str, notification_id: str | None = None) -> str:
    """Mark one or all notifications as read."""
    uid = uuid.UUID(user_id)
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await _ensure_table(session)
                if notification_id:
                    await session.execute(text("""
                        UPDATE notifications SET is_read = true
                        WHERE user_id = :uid AND id = :nid
                    """), {"uid": uid, "nid": uuid.UUID(notification_id)})
                else:
                    await session.execute(text("""
                        UPDATE notifications SET is_read = true
                        WHERE user_id = :uid AND is_read = false
                    """), {"uid": uid})
        return json.dumps({"success": True})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@function_tool
async def notification_tool(user_id: str, event_type: str, message: str) -> str:
    """Push a real-time notification to the user.

    event_type: one of new_jobs_found | draft_ready | email_sent |
                recruiter_replied | followup_due
    message: human-readable notification text.
    """
    return await notification_push_impl(
        user_id=user_id, event_type=event_type, message=message
    )
