from fastapi import APIRouter, Depends, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from db.database import get_db
from db.models import User, JobMatch, ExtractedEmail, PendingEmail, SentEmail, ActivityLog, UserPreference
from api.routes.auth import get_current_user
import json

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

@router.get("/summary")
async def get_summary(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    jobs = (await db.execute(select(JobMatch).where(JobMatch.user_id == current_user.id))).scalars().all()
    drafts = (await db.execute(
        select(PendingEmail).where(PendingEmail.user_id == current_user.id, PendingEmail.status == "pending")
    )).scalars().all()
    logs = (await db.execute(
        select(ActivityLog).where(ActivityLog.user_id == current_user.id).order_by(ActivityLog.logged_at.desc()).limit(20)
    )).scalars().all()

    return {
        "matched_jobs": len([j for j in jobs if j.status == "matched"]),
        "applied_jobs": len([j for j in jobs if j.status == "applied"]),
        "drafts": len(drafts),
        "recent_activity": [
            {"event_type": l.event_type, "detail": l.event_detail, "logged_at": l.logged_at.isoformat()}
            for l in logs
        ],
    }

@router.get("/jobs")
async def get_jobs(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    jobs = (await db.execute(select(JobMatch).where(JobMatch.user_id == current_user.id).order_by(JobMatch.created_at.desc()))).scalars().all()
    return [
        {
            "id": str(j.id), "job_title": j.job_title, "company": j.company,
            "match_score": float(j.match_score or 0),
            "match_tier": j.match_tier or "Good Match",
            "location": j.location, "job_url": j.job_url,
            "source": j.source or "", "portal_type": j.portal_type or "",
            "status": j.status, "created_at": j.created_at.isoformat(),
            "matched_skills": j.matched_skills or [],
            "missing_skills": j.missing_skills or [],
        }
        for j in jobs
    ]

@router.get("/pending")
async def get_pending(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(PendingEmail).where(PendingEmail.user_id == current_user.id).order_by(PendingEmail.created_at.desc())
    )).scalars().all()
    return [
        {"id": str(r.id), "job_id": str(r.job_id) if r.job_id else None, "draft_content": r.draft_content,
         "status": r.status, "created_at": r.created_at.isoformat()}
        for r in rows
    ]

@router.delete("/jobs/clear")
async def clear_jobs(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await db.execute(delete(JobMatch).where(JobMatch.user_id == current_user.id))
    await db.commit()
    return {"success": True}

@router.get("/data/mail")
async def get_mail_data(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(ExtractedEmail).where(ExtractedEmail.user_id == current_user.id))).scalars().all()
    return [{"email": r.email, "source_url": r.source_url, "is_valid": r.is_valid, "job_id": str(r.job_id)} for r in rows]

@router.get("/data/sent")
async def get_sent_data(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(SentEmail).where(SentEmail.user_id == current_user.id).order_by(SentEmail.sent_at.desc()))).scalars().all()
    return [
        {"id": str(r.id), "recipient_email": r.recipient_email, "email_content": r.email_content,
         "resume_attached": r.resume_attached, "sent_at": r.sent_at.isoformat(), "job_id": str(r.job_id)}
        for r in rows
    ]


@router.get("/analytics")
async def get_analytics(current_user: User = Depends(get_current_user)):
    from job_agent.tools.analytics import analytics_impl
    result = json.loads(await analytics_impl(user_id=str(current_user.id)))
    return result


@router.post("/followup")
async def trigger_followup(current_user: User = Depends(get_current_user)):
    from job_agent.tools.email_followup import email_followup_impl
    result = json.loads(await email_followup_impl(
        user_id=str(current_user.id),
        user_name=current_user.name or "Candidate",
    ))
    return result


@router.get("/preferences")
async def get_preferences(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    pref = (await db.execute(
        select(UserPreference).where(UserPreference.user_id == current_user.id)
    )).scalar_one_or_none()
    if not pref:
        return {}
    return {
        "preferred_roles":      pref.preferred_roles or "",
        "preferred_locations":  pref.preferred_locations or "",
        "salary_min":           pref.salary_min,
        "salary_max":           pref.salary_max,
        "job_type":             pref.job_type or "full-time",
        "open_to_remote":       pref.open_to_remote,
    }


@router.post("/preferences")
async def save_preferences(
    preferred_roles: str = "",
    preferred_locations: str = "",
    salary_min: int = None,
    salary_max: int = None,
    job_type: str = "full-time",
    open_to_remote: bool = True,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pref = (await db.execute(
        select(UserPreference).where(UserPreference.user_id == current_user.id)
    )).scalar_one_or_none()

    if pref:
        pref.preferred_roles     = preferred_roles
        pref.preferred_locations = preferred_locations
        pref.salary_min          = salary_min
        pref.salary_max          = salary_max
        pref.job_type            = job_type
        pref.open_to_remote      = open_to_remote
    else:
        import uuid as _uuid
        pref = UserPreference(
            id=_uuid.uuid4(),
            user_id=current_user.id,
            preferred_roles=preferred_roles,
            preferred_locations=preferred_locations,
            salary_min=salary_min,
            salary_max=salary_max,
            job_type=job_type,
            open_to_remote=open_to_remote,
        )
        db.add(pref)

    await db.commit()
    return {"success": True}


# ── Notifications ──────────────────────────────────────────────────────────────

@router.get("/notifications")
async def get_notifications(
    unread_only: bool = True,
    current_user: User = Depends(get_current_user),
):
    from job_agent.tools.notification_tool import notification_list_impl
    result = json.loads(await notification_list_impl(
        user_id=str(current_user.id), unread_only=unread_only
    ))
    return result


@router.post("/notifications/read-all")
async def mark_notifications_read(current_user: User = Depends(get_current_user)):
    from job_agent.tools.notification_tool import notification_mark_read_impl
    result = json.loads(await notification_mark_read_impl(user_id=str(current_user.id)))
    return result


# ── Job alert ─────────────────────────────────────────────────────────────────

@router.get("/job-alert")
async def check_job_alert(current_user: User = Depends(get_current_user)):
    from job_agent.tools.job_alert import job_alert_check_impl
    result = json.loads(await job_alert_check_impl(user_id=str(current_user.id)))
    return result


# ── Resume versions ───────────────────────────────────────────────────────────

@router.get("/resume-versions")
async def get_resume_versions(current_user: User = Depends(get_current_user)):
    from job_agent.tools.resume_version import resume_version_list_impl
    result = json.loads(await resume_version_list_impl(user_id=str(current_user.id)))
    return result


# ── Resume scorer ─────────────────────────────────────────────────────────────

@router.post("/resume-score")
async def score_resume(
    job_id: str = Body(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from job_agent.tools.resume_scorer import resume_scorer_impl
    from job_agent.tools.resume_parser import resume_parser_impl

    job = (await db.execute(
        select(JobMatch).where(
            JobMatch.id == __import__("uuid").UUID(job_id),
            JobMatch.user_id == current_user.id,
        )
    )).scalar_one_or_none()

    if not job:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Job not found")

    resume_text = ""
    if current_user.resume_path:
        parsed = json.loads(await resume_parser_impl(resume_path=current_user.resume_path))
        resume_text = parsed.get("resume_text", "")

    job_json = json.dumps({
        "title": job.job_title,
        "company": job.company,
        "description": "",
    })
    result = json.loads(await resume_scorer_impl(resume_text=resume_text, job_json=job_json))
    return result


# ── Portal blacklist ──────────────────────────────────────────────────────────

@router.get("/portal-blacklist")
async def get_portal_blacklist(current_user: User = Depends(get_current_user)):
    from job_agent.tools.portal_blacklist import portal_blacklist_list_impl
    result = json.loads(await portal_blacklist_list_impl(user_id=str(current_user.id)))
    return result


@router.delete("/portal-blacklist/{portal_name}")
async def reset_portal_blacklist(
    portal_name: str,
    current_user: User = Depends(get_current_user),
):
    from job_agent.tools.portal_blacklist import portal_blacklist_reset_impl
    result = json.loads(await portal_blacklist_reset_impl(
        user_id=str(current_user.id), portal_name=portal_name
    ))
    return result


# ── Email reply detector ──────────────────────────────────────────────────────

@router.get("/email-replies")
async def check_email_replies(current_user: User = Depends(get_current_user)):
    from job_agent.tools.email_reply_detector import email_reply_detector_impl
    result = json.loads(await email_reply_detector_impl(user_id=str(current_user.id)))
    return result


# ── Application status tracker ────────────────────────────────────────────────

@router.get("/applications")
async def get_applications(current_user: User = Depends(get_current_user)):
    from job_agent.tools.application_status_tracker import status_list_impl
    result = json.loads(await status_list_impl(user_id=str(current_user.id)))
    return result


@router.put("/applications/{application_id}/status")
async def update_application_status(
    application_id: str,
    status: str = Body(...),
    notes: dict = Body(default=None),
    current_user: User = Depends(get_current_user),
):
    from job_agent.tools.application_status_tracker import status_update_impl
    result = json.loads(await status_update_impl(
        user_id=str(current_user.id),
        application_id=application_id,
        new_status=status,
        notes=notes,
    ))
    return result
