"""STEP 13 — Update dashboard state (job_matches status, pending count, etc.)."""
import json
import uuid
from agents import function_tool
from db.database import AsyncSessionLocal
from db.models import JobMatch, PendingEmail, SentEmail
from sqlalchemy import select, update


async def task_manager_impl(
    user_id: str,
    job_id: str = "",
    new_status: str = "",
    action: str = "refresh",
) -> str:
    uid = uuid.UUID(user_id)

    async with AsyncSessionLocal() as session:
        async with session.begin():
            if job_id and new_status:
                await session.execute(
                    update(JobMatch)
                    .where(JobMatch.id == uuid.UUID(job_id), JobMatch.user_id == uid)
                    .values(status=new_status)
                )

        matched = (await session.execute(
            select(JobMatch).where(JobMatch.user_id == uid, JobMatch.status == "matched")
        )).scalars().all()
        applied = (await session.execute(
            select(JobMatch).where(JobMatch.user_id == uid, JobMatch.status == "applied")
        )).scalars().all()
        pending = (await session.execute(
            select(PendingEmail).where(PendingEmail.user_id == uid, PendingEmail.status == "pending")
        )).scalars().all()
        sent = (await session.execute(
            select(SentEmail).where(SentEmail.user_id == uid)
        )).scalars().all()

    return json.dumps({
        "success": True,
        "dashboard": {
            "matched_jobs": len(matched),
            "applied_jobs": len(applied),
            "pending_approvals": len(pending),
            "emails_sent": len(sent),
        }
    })


@function_tool
async def task_manager_tool(
    user_id: str,
    job_id: str = "",
    new_status: str = "",
    action: str = "refresh",
) -> str:
    """Update job match status and return dashboard summary counts.
    Returns JSON with dashboard counts.
    """
    return await task_manager_impl(
        user_id=user_id, job_id=job_id, new_status=new_status, action=action,
    )
