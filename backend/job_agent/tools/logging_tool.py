"""STEP 12 — Log pipeline events to activity_log table."""
import json
import uuid
from agents import function_tool
from db.database import AsyncSessionLocal
from db.models import ActivityLog


async def logging_impl(
    user_id: str,
    event_type: str,
    event_detail_json: str = "{}",
) -> str:
    try:
        detail: dict = json.loads(event_detail_json)
        async with AsyncSessionLocal() as session:
            async with session.begin():
                session.add(ActivityLog(
                    user_id=uuid.UUID(user_id),
                    event_type=event_type,
                    event_detail=detail,
                ))
        return json.dumps({"success": True, "event_type": event_type})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@function_tool
async def logging_tool(
    user_id: str,
    event_type: str,
    event_detail_json: str = "{}",
) -> str:
    """Write a structured log entry to the activity_log table.
    event_detail_json: JSON object with arbitrary event metadata.
    Returns JSON with success status.
    """
    return await logging_impl(
        user_id=user_id, event_type=event_type, event_detail_json=event_detail_json,
    )
