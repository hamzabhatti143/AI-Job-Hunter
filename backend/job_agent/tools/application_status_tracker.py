"""application_status_tracker_tool — Track status of portal applications.

Queries the applications table and cross-references with job_matches to
provide a unified view of every application's lifecycle:
  submitted → viewed → rejected | interview | offered

Portal-specific polling (e.g. scraping Workday login) is intentionally
deferred to future browser-automation integration.
"""
import json
import uuid
from datetime import datetime, timezone
from sqlalchemy import select, text
from agents import function_tool
from db.database import AsyncSessionLocal
from db.models import Application, JobMatch


async def status_list_impl(user_id: str) -> str:
    """Return all applications with current status for a user."""
    uid = uuid.UUID(user_id)
    try:
        async with AsyncSessionLocal() as session:
            apps = (await session.execute(
                select(Application, JobMatch)
                .join(JobMatch, Application.job_id == JobMatch.id, isouter=True)
                .where(Application.user_id == uid)
                .order_by(Application.applied_at.desc())
            )).all()

        return json.dumps({
            "success": True,
            "applications": [
                {
                    "id":              str(a.Application.id),
                    "job_title":       a.JobMatch.job_title if a.JobMatch else "Unknown",
                    "company":         a.JobMatch.company   if a.JobMatch else "Unknown",
                    "method":          a.Application.method,
                    "portal_name":     a.Application.portal_name or "",
                    "status":          a.Application.status,
                    "confirmation_id": a.Application.confirmation_id or "",
                    "applied_at":      a.Application.applied_at.isoformat(),
                    "notes":           a.Application.notes or {},
                }
                for a in apps
            ],
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


async def status_update_impl(
    user_id: str,
    application_id: str,
    new_status: str,
    notes: dict | None = None,
) -> str:
    """Manually update an application's status (e.g. after recruiter contact)."""
    uid = uuid.UUID(user_id)
    valid_statuses = {"submitted", "viewed", "interview", "rejected", "offered", "withdrawn"}
    if new_status not in valid_statuses:
        return json.dumps({"success": False, "error": f"Invalid status. Must be one of: {', '.join(valid_statuses)}"})

    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                app = (await session.execute(
                    select(Application).where(
                        Application.id == uuid.UUID(application_id),
                        Application.user_id == uid,
                    )
                )).scalar_one_or_none()

                if not app:
                    return json.dumps({"success": False, "error": "Application not found."})

                app.status = new_status
                if notes:
                    app.notes = {**(app.notes or {}), **notes}

        return json.dumps({"success": True, "new_status": new_status})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


async def status_record_impl(
    user_id: str,
    job_id: str,
    method: str,
    portal_name: str = "",
    confirmation_id: str = "",
    notes: dict | None = None,
) -> str:
    """Record a new application submission in the applications table."""
    uid = uuid.UUID(user_id)
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                app = Application(
                    id=uuid.uuid4(),
                    user_id=uid,
                    job_id=uuid.UUID(job_id) if job_id else None,
                    method=method,
                    portal_name=portal_name or None,
                    confirmation_id=confirmation_id or None,
                    status="submitted",
                    notes=notes,
                )
                session.add(app)

        return json.dumps({
            "success":         True,
            "application_id":  str(app.id),
            "method":          method,
            "status":          "submitted",
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@function_tool
async def application_status_tracker_tool(user_id: str) -> str:
    """List all job applications and their current statuses.

    Returns applications with job title, company, method (email/portal),
    status (submitted | viewed | interview | rejected | offered), and timeline.
    """
    return await status_list_impl(user_id=user_id)
