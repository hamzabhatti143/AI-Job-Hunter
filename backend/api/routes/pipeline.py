from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
import asyncio, os, uuid, json, traceback, smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from db.database import get_db, AsyncSessionLocal
from db.models import User, JobMatch, PendingEmail, SentEmail
from api.routes.auth import get_current_user, invalidate_user_cache
from fastapi.security import OAuth2PasswordBearer
_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
from job_agent.pipeline import run_pipeline

router = APIRouter(prefix="/pipeline", tags=["pipeline"])

# In-memory task store: task_id → {"status": "running"|"done"|"error", "result": {...}}
_pipeline_tasks: dict[str, dict] = {}

# Per-job apply task store: job_id → {"status": "queued"|"running"|"done"|"error", "result": {...}}
_apply_tasks: dict[str, dict] = {}

UPLOAD_DIR = os.path.abspath(os.getenv("UPLOAD_DIR", "./uploads"))
RESUME_DIR = os.path.join(UPLOAD_DIR, "resumes")
os.makedirs(RESUME_DIR, exist_ok=True)


def _delete_file(path: str):
    """Silently delete a file if it exists."""
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


async def _run_pipeline_task(
    task_id: str,
    user_id: str,
    tmp_path: str,
    location: str,
    role_preference: str,
    api_key: str,
    user_email: str,
    recruiter_email: str,
):
    """Run the pipeline as a background coroutine, storing result in _pipeline_tasks."""
    try:
        result = await run_pipeline(
            user_id=user_id,
            resume_path=tmp_path,
            location=location,
            role_preference=role_preference,
            api_key=api_key,
            user_email=user_email,
            recruiter_email=recruiter_email,
        )
        _pipeline_tasks[task_id] = {"status": "done", "result": result}
    except Exception as exc:
        traceback.print_exc()
        _pipeline_tasks[task_id] = {"status": "error", "result": {"error": str(exc)}}
    finally:
        _delete_file(tmp_path)


@router.post("/start")
async def start_pipeline(
    resume: UploadFile = File(...),
    location: str = Form(...),
    role_preference: str = Form(...),
    api_key: str = Form(""),
    recruiter_email: str = Form(""),
    token: str = Depends(_oauth2_scheme),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start pipeline as background task. Returns task_id immediately — poll /pipeline/status/{task_id}."""
    ext = os.path.splitext(resume.filename or "resume.pdf")[1].lower()
    if ext not in (".pdf", ".docx", ".doc"):
        raise HTTPException(status_code=400, detail="Only PDF or DOCX resumes accepted")

    # Save resume files
    tmp_name = f"{current_user.id}_{uuid.uuid4()}{ext}"
    tmp_path = os.path.join(UPLOAD_DIR, tmp_name)
    perm_name = f"{current_user.id}_resume{ext}"
    perm_path = os.path.join(RESUME_DIR, perm_name)

    content = await resume.read()
    with open(tmp_path, "wb") as f:
        f.write(content)
    with open(perm_path, "wb") as f:
        f.write(content)

    # Update stored resume path — only delete old file if it differs from the new one
    new_abs = os.path.abspath(perm_path)
    old_abs = os.path.abspath(current_user.resume_path) if current_user.resume_path else ""
    if old_abs and old_abs != new_abs:
        _delete_file(old_abs)
    current_user.resume_path = new_abs
    current_user.resume_original_name = resume.filename or f"Resume{ext}"
    db.add(current_user)
    await db.commit()
    invalidate_user_cache(token)  # flush stale cached user so resume_path is fresh on next request

    # Create task entry and schedule on the running event loop
    task_id = str(uuid.uuid4())
    _pipeline_tasks[task_id] = {"status": "running", "result": None}

    asyncio.create_task(
        _run_pipeline_task(
            task_id=task_id,
            user_id=str(current_user.id),
            tmp_path=tmp_path,
            location=location,
            role_preference=role_preference,
            api_key=api_key,
            user_email=current_user.email,
            recruiter_email=recruiter_email,
        )
    )

    return {"task_id": task_id, "status": "running"}


@router.get("/status/{task_id}")
async def pipeline_status(task_id: str, current_user: User = Depends(get_current_user)):
    """Poll for pipeline task status. Returns {status, result} when done."""
    task = _pipeline_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


async def _run_apply_job_task(
    job_id: str,
    user_id: str,
    user_email: str,
    user_name: str,
    resume_path: str,
    resume_original_name: str,
):
    """Background: parse resume for name/email/phone, write email via Gemini, save draft."""
    from job_agent.tools.email_writer import (
        email_writer_impl,
        _extract_phone,
        _extract_email_from_resume,
        _extract_name_from_resume,
    )

    _apply_tasks[job_id] = {"status": "running", "result": None}
    try:
        async with AsyncSessionLocal() as db:
            job = (await db.execute(
                select(JobMatch).where(JobMatch.id == uuid.UUID(job_id))
            )).scalar_one_or_none()
            if not job:
                _apply_tasks[job_id] = {"status": "error", "result": {"error": "Job not found"}}
                return

            # Parse resume to extract name, email, phone
            resume_text = ""
            if resume_path and os.path.exists(resume_path):
                try:
                    from job_agent.tools.resume_parser import resume_parser_impl
                    parsed = json.loads(await resume_parser_impl(resume_path=resume_path))
                    resume_text = parsed.get("resume_text", "")
                except Exception:
                    pass

            resume_name  = _extract_name_from_resume(resume_text)  if resume_text else ""
            resume_email = _extract_email_from_resume(resume_text)  if resume_text else ""
            resume_phone = _extract_phone(resume_text)              if resume_text else ""

            # Use resume values with fallback to account profile values
            effective_name  = resume_name  or user_name  or "Candidate"
            effective_email = user_email or ""
            effective_phone = resume_phone

            result = json.loads(await email_writer_impl(
                job_title=job.job_title or "",
                company_name=job.company or "",
                job_url=job.job_url or "",
                user_name=effective_name,
                user_email=effective_email,
                user_phone=effective_phone,
            ))
            if result.get("status") != "ready":
                _apply_tasks[job_id] = {"status": "error", "result": {"error": result.get("error", "Could not generate template. Try Regenerate or write manually.")}}
                return

            draft_id = uuid.uuid4()
            db.add(PendingEmail(
                id=draft_id,
                user_id=uuid.UUID(user_id),
                job_id=uuid.UUID(job_id),
                draft_content=json.dumps(result),
                status="pending",
            ))
            await db.commit()

            _apply_tasks[job_id] = {
                "status": "done",
                "result": {
                    "success":         True,
                    "draft_id":        str(draft_id),
                    "job_title":       result.get("job_title", job.job_title),
                    "company":         result.get("company", job.company),
                    "subject":         result.get("subject", ""),
                    "body":            result.get("body", ""),
                    "to_email":        "",
                    "resume_filename": resume_original_name or "",
                },
            }
    except Exception as exc:
        traceback.print_exc()
        _apply_tasks[job_id] = {"status": "error", "result": {"error": str(exc)}}


@router.post("/apply-job/{job_id}")
async def apply_to_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Queue a background email-draft task. Returns 202 immediately — poll /pipeline/apply-status/{job_id}."""
    try:
        job = (await db.execute(
            select(JobMatch).where(
                JobMatch.id == uuid.UUID(job_id),
                JobMatch.user_id == current_user.id,
            )
        )).scalar_one_or_none()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        _apply_tasks[job_id] = {"status": "queued", "result": None}
        asyncio.create_task(_run_apply_job_task(
            job_id=job_id,
            user_id=str(current_user.id),
            user_email=current_user.email,
            user_name=current_user.name or "",
            resume_path=current_user.resume_path or "",
            resume_original_name=current_user.resume_original_name or "",
        ))

        return JSONResponse(
            status_code=202,
            content={"status": "queued", "job_id": job_id, "message": "Application pipeline started."},
            headers={"Connection": "keep-alive", "Keep-Alive": "timeout=120, max=100"},
        )
    except HTTPException:
        raise
    except Exception as exc:
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(exc), "job_id": job_id},
        )


@router.get("/apply-status/{job_id}")
async def apply_job_status(job_id: str, current_user: User = Depends(get_current_user)):
    """Poll apply-job background task status."""
    task = _apply_tasks.get(job_id)
    if not task:
        return JSONResponse(
            content={"status": "not_found", "job_id": job_id},
            headers={"Connection": "keep-alive"},
        )
    return JSONResponse(
        content={"job_id": job_id, **task},
        headers={"Connection": "keep-alive"},
    )


@router.put("/draft/{draft_id}")
async def update_draft(
    draft_id: str,
    subject: str = Form(""),
    body: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update the subject/body of a pending draft (user edits in composer)."""
    draft = (await db.execute(
        select(PendingEmail).where(
            PendingEmail.id == uuid.UUID(draft_id),
            PendingEmail.user_id == current_user.id,
            PendingEmail.status == "pending",
        )
    )).scalar_one_or_none()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found or already sent")

    try:
        content = json.loads(draft.draft_content)
    except Exception:
        content = {}

    if subject:
        content["subject"] = subject
    if body:
        content["body"] = body

    await db.execute(
        update(PendingEmail)
        .where(PendingEmail.id == uuid.UUID(draft_id))
        .values(draft_content=json.dumps(content))
    )
    await db.commit()
    return {"success": True}


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


@router.post("/send/{draft_id}")
async def send_draft_email(
    draft_id: str,
    recipient_email: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a drafted email via the user's configured SMTP credentials."""
    # Always re-fetch from DB to get the latest resume_path — the cached user object
    # from get_current_user may be stale if the resume was uploaded in this session.
    fresh_user = (await db.execute(select(User).where(User.id == current_user.id))).scalar_one_or_none()
    u = fresh_user or current_user

    user_id       = u.id
    smtp_host     = u.smtp_host
    smtp_port     = u.smtp_port or 587
    smtp_user     = u.smtp_user
    smtp_password = u.smtp_password
    resume_path   = u.resume_path
    resume_name   = u.resume_original_name

    if not (smtp_host and smtp_user and smtp_password):
        raise HTTPException(
            status_code=400,
            detail="SMTP not configured. Go to Settings to add your email credentials."
        )

    # Load draft
    draft = (await db.execute(
        select(PendingEmail).where(
            PendingEmail.id == uuid.UUID(draft_id),
            PendingEmail.user_id == user_id,
        )
    )).scalar_one_or_none()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    try:
        content = json.loads(draft.draft_content)
    except Exception:
        content = {"subject": "Job Application", "body": draft.draft_content}

    subject = content.get("subject", "Job Application")
    body = content.get("body", "")

    # Build MIME message
    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = recipient_email
    msg.attach(MIMEText(body, "plain"))

    # Resolve resume path — fall back to scanning RESUME_DIR if stored path is stale
    def _resolve_resume(stored_path: str, uid: str) -> str:
        if stored_path and os.path.exists(stored_path):
            return stored_path
        try:
            for fname in os.listdir(RESUME_DIR):
                if fname.startswith(uid):
                    return os.path.join(RESUME_DIR, fname)
        except Exception:
            pass
        return ""

    resolved_resume = _resolve_resume(resume_path or "", str(user_id))

    # Attach resume
    resume_attached = False
    attached_filename = ""
    if resolved_resume:
        try:
            with open(resolved_resume, "rb") as rf:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(rf.read())
            encoders.encode_base64(part)
            attached_filename = resume_name or os.path.basename(resolved_resume)
            part.add_header("Content-Disposition", "attachment", filename=attached_filename)
            msg.attach(part)
            resume_attached = True
        except Exception as e:
            traceback.print_exc()

    # Send via SMTP
    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, recipient_email, msg.as_string())
    except smtplib.SMTPAuthenticationError:
        raise HTTPException(status_code=400, detail="SMTP authentication failed. Check your email credentials in Settings.")
    except smtplib.SMTPRecipientsRefused:
        raise HTTPException(status_code=400, detail=f"Recipient email '{recipient_email}' was refused by the mail server.")
    except smtplib.SMTPException as exc:
        raise HTTPException(status_code=500, detail=f"SMTP error: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to send email: {exc}")

    # Record in sent_emails
    db.add(SentEmail(
        user_id=user_id,
        job_id=draft.job_id,
        pending_id=draft.id,
        recipient_email=recipient_email,
        email_content=draft.draft_content,
        resume_attached=resume_attached,
    ))
    await db.execute(
        update(PendingEmail)
        .where(PendingEmail.id == uuid.UUID(draft_id))
        .values(status="sent")
    )
    await db.commit()

    return {
        "success":           True,
        "message":           f"Email sent to {recipient_email}",
        "resume_attached":   resume_attached,
        "resume_filename":   attached_filename,
    }
