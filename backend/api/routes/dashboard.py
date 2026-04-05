from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from db.database import get_db
from db.models import User, JobMatch, ExtractedEmail, PendingEmail, SentEmail, ActivityLog
from api.routes.auth import get_current_user

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
            "match_score": float(j.match_score or 0), "location": j.location,
            "job_url": j.job_url, "status": j.status, "created_at": j.created_at.isoformat(),
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
