from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
import asyncio, os, uuid, json, traceback, smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from db.database import get_db
from db.models import User, JobMatch, PendingEmail, SentEmail
from api.routes.auth import get_current_user
from job_agent.pipeline import run_pipeline

router = APIRouter(prefix="/pipeline", tags=["pipeline"])

# In-memory task store: task_id → {"status": "running"|"done"|"error", "result": {...}}
_pipeline_tasks: dict[str, dict] = {}

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
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

    # Update stored resume path
    _delete_file(current_user.resume_path or "")
    current_user.resume_path = os.path.abspath(perm_path)
    current_user.resume_original_name = resume.filename or f"Resume{ext}"
    db.add(current_user)
    await db.commit()

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


@router.post("/apply-job/{job_id}")
async def apply_to_job(
    job_id: str,
    api_key: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Draft an application email for a specific matched job.
    Runs email finder for this single job (fast — 1 job, not all matches).
    """
    from job_agent.tools.email_writer import email_writer_impl
    from job_agent.tools.email_finder import email_finder_impl

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
        # ── Load resume text for grounded email generation ─────────────────────
        resume_text = ""
        resume_path = current_user.resume_path or ""
        if resume_path and os.path.exists(resume_path):
            try:
                from job_agent.tools.resume_parser import resume_parser_impl
                parsed = json.loads(await resume_parser_impl(resume_path=resume_path))
                resume_text = parsed.get("resume_text", "")
            except Exception:
                pass

        # ── Find recruiter email for this one job ──────────────────────────────
        recruiter_email_found = ""
        email_source = ""
        try:
            job_stub = [{"url": job.job_url or "", "company": job.company or "",
                         "title": job.job_title, "db_job_id": str(job.id)}]
            finder_result = json.loads(await email_finder_impl(json.dumps(job_stub)))
            er = (finder_result.get("email_results") or [{}])[0]
            if er.get("is_valid") and er.get("email"):
                recruiter_email_found = er["email"]
                email_source = er.get("source", "")
        except Exception:
            pass  # email finding is best-effort — never block draft creation

        # ── Draft the application email ────────────────────────────────────────
        step7 = json.loads(await email_writer_impl(
            job_json=json.dumps({"title": job.job_title, "company": job.company, "url": job.job_url or "", "description": ""}),
            skills_json=json.dumps([]),
            user_name=current_user.name or "Candidate",
            user_email=current_user.email,
            api_key=api_key,
            recruiter_email=recruiter_email_found,
            resume_text=resume_text,
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
            "success":          True,
            "draft_id":         str(draft_id),
            "job_title":        job.job_title,
            "company":          job.company,
            "recruiter_email":  recruiter_email_found or None,
            "email_source":     email_source or None,
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


@router.post("/send/{draft_id}")
async def send_draft_email(
    draft_id: str,
    recipient_email: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a drafted email via the user's configured SMTP credentials."""
    # Snapshot all user fields immediately — prevents DetachedInstanceError if the
    # ORM instance loses its session binding during the async SMTP call below.
    user_id       = current_user.id
    smtp_host     = current_user.smtp_host
    smtp_port     = current_user.smtp_port or 587
    smtp_user     = current_user.smtp_user
    smtp_password = current_user.smtp_password
    resume_path   = current_user.resume_path
    resume_name   = current_user.resume_original_name

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

    # Attach resume if available
    resume_attached = False
    if resume_path and os.path.exists(resume_path):
        try:
            with open(resume_path, "rb") as rf:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(rf.read())
            encoders.encode_base64(part)
            display_name = resume_name or os.path.basename(resume_path)
            part.add_header("Content-Disposition", "attachment", filename=display_name)
            msg.attach(part)
            resume_attached = True
        except Exception:
            pass

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

    return {"success": True, "message": f"Email sent to {recipient_email}"}
