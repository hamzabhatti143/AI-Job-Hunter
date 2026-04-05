from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
import os, shutil, uuid, json, traceback
from db.database import get_db
from db.models import User, JobMatch, PendingEmail
from api.routes.auth import get_current_user
from job_agent.pipeline import run_pipeline

router = APIRouter(prefix="/pipeline", tags=["pipeline"])

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _delete_file(path: str):
    """Silently delete a file if it exists."""
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


@router.post("/start")
async def start_pipeline(
    resume: UploadFile = File(...),
    location: str = Form(...),
    role_preference: str = Form(...),
    api_key: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ext = os.path.splitext(resume.filename)[1].lower()
    if ext not in (".pdf", ".docx", ".doc"):
        raise HTTPException(status_code=400, detail="Only PDF or DOCX resumes accepted")

    filename = f"{current_user.id}_{uuid.uuid4()}{ext}"
    save_path = os.path.join(UPLOAD_DIR, filename)
    with open(save_path, "wb") as f:
        shutil.copyfileobj(resume.file, f)

    # Clear any old resume file for this user before saving the new path
    _delete_file(current_user.resume_path or "")
    current_user.resume_path = save_path
    db.add(current_user)
    await db.commit()

    try:
        result = await run_pipeline(
            user_id=str(current_user.id),
            resume_path=save_path,
            location=location,
            role_preference=role_preference,
            api_key=api_key,
            user_email=current_user.email,
        )
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        # Delete the uploaded file — it has been fully processed
        _delete_file(save_path)
        current_user.resume_path = None
        db.add(current_user)
        await db.commit()

    return result


@router.post("/apply-job/{job_id}")
async def apply_to_job(
    job_id: str,
    api_key: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Draft an application email for a specific matched job."""
    from job_agent.tools.email_writer import email_writer_impl

    job = (await db.execute(
        select(JobMatch).where(
            JobMatch.id == uuid.UUID(job_id),
            JobMatch.user_id == current_user.id,
        )
    )).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status == "applied":
        raise HTTPException(status_code=400, detail="Already drafted an application for this job")

    try:
        # Resume file is deleted after pipeline — use stored user info directly
        step7 = json.loads(await email_writer_impl(
            job_json=json.dumps({"title": job.job_title, "company": job.company, "url": job.job_url or ""}),
            skills_json=json.dumps([]),
            user_name=current_user.name or "Candidate",
            user_email=current_user.email,
            api_key=api_key,
            recruiter_email="",
        ))
        if not step7.get("success"):
            raise HTTPException(status_code=500, detail=step7.get("error", "Draft generation failed"))

        draft_id = uuid.uuid4()
        db.add(PendingEmail(
            id=draft_id,
            user_id=current_user.id,
            job_id=uuid.UUID(job_id),
            draft_content=json.dumps(step7),
            status="pending",
        ))
        await db.execute(
            update(JobMatch).where(JobMatch.id == uuid.UUID(job_id)).values(status="applied")
        )
        await db.commit()

        return {
            "success": True,
            "draft_id": str(draft_id),
            "job_title": job.job_title,
            "company": job.company,
        }
    except HTTPException:
        raise
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/draft/{draft_id}")
async def delete_draft(
    draft_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        update(PendingEmail)
        .where(PendingEmail.id == uuid.UUID(draft_id), PendingEmail.user_id == current_user.id)
        .values(status="rejected")
    )
    await db.commit()
    return {"success": True}
