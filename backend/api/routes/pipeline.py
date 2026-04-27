from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders as email_encoders
import asyncio, os, uuid, json, traceback, httpx, base64
from db.database import get_db, AsyncSessionLocal
from db.models import User, JobMatch, PendingEmail, SentEmail, utcnow
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


async def _get_valid_gmail_token(user: User, db: AsyncSession) -> str:
    """Return a valid Gmail access token, refreshing it if expired or near-expiry."""
    now = datetime.now(timezone.utc)
    needs_refresh = (
        not user.gmail_access_token
        or not user.gmail_token_expiry
        or user.gmail_token_expiry <= now + timedelta(minutes=2)
    )
    if needs_refresh:
        if not user.gmail_refresh_token:
            raise ValueError("Gmail not connected — please connect Gmail in Settings")
        async with httpx.AsyncClient() as client:
            r = await client.post("https://oauth2.googleapis.com/token", data={
                "client_id":     user.google_client_id     or os.getenv("GOOGLE_CLIENT_ID", ""),
                "client_secret": user.google_client_secret or os.getenv("GOOGLE_CLIENT_SECRET", ""),
                "refresh_token": user.gmail_refresh_token,
                "grant_type":    "refresh_token",
            })
            if r.status_code != 200:
                raise ValueError("Gmail token refresh failed — please reconnect Gmail in Settings")
            tokens = r.json()
        user.gmail_access_token = tokens["access_token"]
        user.gmail_token_expiry = datetime.now(timezone.utc) + timedelta(seconds=tokens.get("expires_in", 3600))
        db.add(user)
        await db.commit()
    return user.gmail_access_token


async def _send_via_gmail(
    user: User,
    db: AsyncSession,
    to: str,
    subject: str,
    body: str,
    attachment_bytes: bytes | None = None,
    attachment_name: str | None = None,
) -> str:
    """Send via Gmail API. Returns threadId for reply tracking."""
    access_token = await _get_valid_gmail_token(user, db)

    msg = MIMEMultipart()
    msg["To"]      = to
    msg["From"]    = user.email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    if attachment_bytes and attachment_name:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(attachment_bytes)
        email_encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=attachment_name)
        msg.attach(part)

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"raw": raw},
            timeout=15,
        )
        if r.status_code >= 400:
            raise ValueError(f"Gmail API error {r.status_code}: {r.text}")
        return r.json().get("threadId", "")


def _extract_gmail_body(message: dict) -> str:
    """Extract plain text from a Gmail message payload."""
    payload = message.get("payload", {})
    data = payload.get("body", {}).get("data", "")
    if data:
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    for part in payload.get("parts", []):
        if part.get("mimeType") == "text/plain":
            data = part.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    return ""


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
    """Send a drafted email via Gmail API."""
    # Always re-fetch from DB to get the latest resume_path and Gmail tokens
    fresh_user = (await db.execute(select(User).where(User.id == current_user.id))).scalar_one_or_none()
    u = fresh_user or current_user

    if not u.gmail_refresh_token:
        raise HTTPException(
            status_code=400,
            detail="Gmail not connected. Connect Gmail in Settings to send emails."
        )
    user_id    = u.id
    resume_path = u.resume_path
    resume_name = u.resume_original_name

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
    body    = content.get("body", "")

    sent_id = uuid.uuid4()

    # Resolve and read resume bytes
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
    attachment_bytes: bytes | None = None
    attached_filename = ""
    resume_attached = False

    if resolved_resume:
        try:
            with open(resolved_resume, "rb") as rf:
                attachment_bytes = rf.read()
            attached_filename = resume_name or os.path.basename(resolved_resume)
            resume_attached = True
        except Exception:
            traceback.print_exc()

    try:
        gmail_thread_id = await _send_via_gmail(
            user=u, db=db, to=recipient_email, subject=subject, body=body,
            attachment_bytes=attachment_bytes, attachment_name=attached_filename or None,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to send email: {exc}")

    # Record send
    db.add(SentEmail(
        id=sent_id,
        user_id=user_id,
        job_id=draft.job_id,
        pending_id=draft.id,
        recipient_email=recipient_email,
        email_content=draft.draft_content,
        resume_attached=resume_attached,
        gmail_thread_id=gmail_thread_id or None,
    ))
    await db.execute(
        update(PendingEmail)
        .where(PendingEmail.id == uuid.UUID(draft_id))
        .values(status="sent")
    )
    await db.commit()

    return {
        "success":         True,
        "message":         f"Email sent to {recipient_email}",
        "resume_attached": resume_attached,
        "resume_filename": attached_filename,
    }


@router.post("/check-replies")
async def check_replies(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Poll Gmail threads for recruiter replies. Called when user opens Sent page."""
    if not current_user.gmail_refresh_token:
        return {"checked": 0, "new_replies": 0}

    rows = (await db.execute(
        select(SentEmail).where(
            SentEmail.user_id == current_user.id,
            SentEmail.gmail_thread_id.isnot(None),
            SentEmail.replied_at.is_(None),
        )
    )).scalars().all()

    if not rows:
        return {"checked": 0, "new_replies": 0}

    fresh = (await db.execute(select(User).where(User.id == current_user.id))).scalar_one_or_none()
    u = fresh or current_user

    try:
        access_token = await _get_valid_gmail_token(u, db)
    except Exception:
        return {"checked": 0, "new_replies": 0}

    new_replies = 0
    async with httpx.AsyncClient() as client:
        for sent in rows:
            try:
                r = await client.get(
                    f"https://gmail.googleapis.com/gmail/v1/users/me/threads/{sent.gmail_thread_id}",
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=10,
                )
                if r.status_code != 200:
                    continue
                messages = r.json().get("messages", [])
                if len(messages) <= 1:
                    continue
                reply_text = _extract_gmail_body(messages[1])
                sent.replied_at    = utcnow()
                sent.reply_content = reply_text[:5000]
                db.add(sent)
                new_replies += 1
            except Exception:
                continue

    if new_replies:
        await db.commit()

    return {"checked": len(rows), "new_replies": new_replies}


@router.post("/find-emails/{job_id}")
async def find_emails_for_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search Google + scrape company pages and return all found recruiter emails for a job."""
    from job_agent.tools.email_finder import (
        _get_search_domain, _company_to_domain_variants, _scrape_emails,
        _serpapi_email_search, _hunter_search, _generate_hr_emails,
        _clean_emails, AGGREGATOR_DOMAINS, _extract_domain_from_url,
        EMAIL_RE, _find_obfuscated_emails, _CAREER_PATHS, _CONTACT_PATHS,
        _is_system_email, RFC5322_RE,
    )
    import re

    job = (await db.execute(
        select(JobMatch).where(
            JobMatch.id == uuid.UUID(job_id),
            JobMatch.user_id == current_user.id,
        )
    )).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    company = job.company or ""
    url = job.job_url or ""
    domain = _get_search_domain(url, company)
    domain_variants = _company_to_domain_variants(company) if company else []
    if domain and domain not in domain_variants:
        domain_variants.insert(0, domain)

    # Collect emails from all sources, labelled by source
    found: list[dict] = []
    seen: set[str] = set()

    def _add(emails: list[str], source: str):
        for e in emails:
            e = e.lower().strip()
            if e and e not in seen and not _is_system_email(e):
                seen.add(e)
                found.append({"address": e, "source": source})

    async with httpx.AsyncClient(follow_redirects=True) as client:
        # 1. Job listing page
        if url and not any(agg in _extract_domain_from_url(url) for agg in AGGREGATOR_DOMAINS):
            _add(await _scrape_emails(client, url), "job listing")

        # 2. Careers pages
        if domain:
            for path in _CAREER_PATHS[:4]:
                _add(await _scrape_emails(client, f"https://{domain}{path}"), "careers page")

        # 3. Contact pages
        if domain:
            for path in _CONTACT_PATHS[:4]:
                _add(await _scrape_emails(client, f"https://{domain}{path}"), "contact page")

        # 4. SerpAPI Google search
        if company:
            _add(await _serpapi_email_search(client, company, domain), "Google search")

        # 5. Hunter.io
        if domain:
            _add(await _hunter_search(client, domain), "Hunter.io")

        # 6. LinkedIn
        if company:
            company_slug = re.sub(r"[^a-z0-9]", "-", company.lower()).strip("-")
            _add(await _scrape_emails(client, f"https://www.linkedin.com/company/{company_slug}/people/"), "LinkedIn")

        # 7. HR email patterns
        for dv in domain_variants[:3]:
            hr = await _generate_hr_emails(dv)
            _add(hr, "pattern (hr@/jobs@/careers@)")

    return {"emails": found, "company": company}


from pydantic import BaseModel

class BulkSendItem(BaseModel):
    draft_id: str
    recipient_email: str

class BulkSendRequest(BaseModel):
    items: list[BulkSendItem]


@router.post("/bulk-send-emails")
async def bulk_send_emails_json(
    req: BulkSendRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send multiple drafted emails at once. Each item needs draft_id + recipient_email."""
    fresh_user = (await db.execute(select(User).where(User.id == current_user.id))).scalar_one_or_none()
    u = fresh_user or current_user

    if not u.gmail_refresh_token:
        raise HTTPException(status_code=400, detail="Gmail not connected. Connect Gmail in Settings to send emails.")

    results = []
    for item in req.items:
        try:
            draft = (await db.execute(
                select(PendingEmail).where(
                    PendingEmail.id == uuid.UUID(item.draft_id),
                    PendingEmail.user_id == current_user.id,
                    PendingEmail.status == "pending",
                )
            )).scalar_one_or_none()
            if not draft:
                results.append({"draft_id": item.draft_id, "success": False, "error": "Draft not found or already sent"})
                continue

            try:
                content = json.loads(draft.draft_content)
            except Exception:
                content = {"subject": "Job Application", "body": draft.draft_content}

            subject = content.get("subject", "Job Application")
            body    = content.get("body", "")

            # Resolve resume
            resume_path = u.resume_path or ""
            resolved_resume = ""
            if resume_path and os.path.exists(resume_path):
                resolved_resume = resume_path
            else:
                for fname in os.listdir(RESUME_DIR):
                    if fname.startswith(str(u.id)):
                        resolved_resume = os.path.join(RESUME_DIR, fname)
                        break

            attachment_bytes: bytes | None = None
            attached_filename = ""
            if resolved_resume:
                try:
                    with open(resolved_resume, "rb") as rf:
                        attachment_bytes = rf.read()
                    attached_filename = u.resume_original_name or os.path.basename(resolved_resume)
                except Exception:
                    pass

            sent_id = uuid.uuid4()
            gmail_thread_id = await _send_via_gmail(
                user=u, db=db, to=item.recipient_email,
                subject=subject, body=body,
                attachment_bytes=attachment_bytes,
                attachment_name=attached_filename or None,
            )

            db.add(SentEmail(
                id=sent_id,
                user_id=u.id,
                job_id=draft.job_id,
                pending_id=draft.id,
                recipient_email=item.recipient_email,
                email_content=draft.draft_content,
                resume_attached=bool(attachment_bytes),
                gmail_thread_id=gmail_thread_id or None,
            ))
            await db.execute(
                update(PendingEmail)
                .where(PendingEmail.id == uuid.UUID(item.draft_id))
                .values(status="sent")
            )
            await db.commit()
            results.append({"draft_id": item.draft_id, "success": True, "recipient": item.recipient_email})

        except Exception as exc:
            results.append({"draft_id": item.draft_id, "success": False, "error": str(exc)})

    sent_count = sum(1 for r in results if r["success"])
    return {"results": results, "sent": sent_count, "total": len(results)}

