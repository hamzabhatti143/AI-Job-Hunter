"""STEP 9 — Save draft email to DB and send preview to user for approval."""
import os
import json
import uuid as uuid_module
import aiosmtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from agents import function_tool
from db.database import AsyncSessionLocal
from db.models import PendingEmail


async def approval_handler_impl(
    draft_email_json: str,
    user_email: str,
    user_id: str,
    job_id: str = "",
    smtp_host: str = "",
    smtp_port: int = 587,
    smtp_user: str = "",
    smtp_password: str = "",
    frontend_url: str = "",
) -> str:
    draft: dict = json.loads(draft_email_json)
    pending_id = str(uuid_module.uuid4())

    db_error = None
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                session.add(PendingEmail(
                    id=uuid_module.UUID(pending_id),
                    user_id=uuid_module.UUID(user_id),
                    job_id=uuid_module.UUID(job_id) if job_id else None,
                    draft_content=json.dumps(draft),
                    status="pending",
                ))
    except Exception as e:
        db_error = str(e)

    host = smtp_host or os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = smtp_port or int(os.getenv("SMTP_PORT", 587))
    user = smtp_user or os.getenv("SMTP_USER", "")
    password = smtp_password or os.getenv("SMTP_PASSWORD", "")
    from_email = user or os.getenv("FROM_EMAIL", "")
    base_url = frontend_url or os.getenv("FRONTEND_URL", "http://localhost:3000")

    approve_url = f"{base_url}/pending?id={pending_id}&action=approve"
    reject_url = f"{base_url}/pending?id={pending_id}&action=reject"

    preview_body = f"""You have a pending job application email waiting for your approval.

--- DRAFT EMAIL PREVIEW ---
To: {draft.get('recipient', '(recruiter email)')}
Subject: {draft.get('subject', '')}

{draft.get('body', '')}
--- END PREVIEW ---

APPROVE (sends to recruiter): {approve_url}
REJECT (discards draft):      {reject_url}
"""

    msg = MIMEMultipart()
    msg["From"] = from_email
    msg["To"] = user_email
    msg["Subject"] = f"[Job Agent] Review: {draft.get('subject', 'Pending Email')}"
    msg.attach(MIMEText(preview_body, "plain"))

    send_error = None
    if user and password:
        try:
            await aiosmtplib.send(
                msg, hostname=host, port=port,
                username=user, password=password, start_tls=True,
            )
        except Exception as e:
            send_error = str(e)

    result = {
        "success": True,
        "pending_id": pending_id,
        "preview_sent_to": user_email,
        "status": "awaiting_approval",
    }
    if db_error:
        result["db_warning"] = db_error
    if send_error:
        result["email_warning"] = send_error
    return json.dumps(result)


@function_tool
async def approval_handler_tool(
    draft_email_json: str,
    user_email: str,
    user_id: str,
    job_id: str = "",
    smtp_host: str = "",
    smtp_port: int = 587,
    smtp_user: str = "",
    smtp_password: str = "",
    frontend_url: str = "",
) -> str:
    """Save draft email to DB and send a preview to the user's email for approval.
    draft_email_json: JSON object with subject, body, recipient fields.
    user_id: UUID string of the authenticated user.
    job_id: db_job_id from the matched job.
    Returns JSON with success status and pending_id (generated internally).
    """
    return await approval_handler_impl(
        draft_email_json=draft_email_json, user_email=user_email, user_id=user_id,
        job_id=job_id, smtp_host=smtp_host, smtp_port=smtp_port,
        smtp_user=smtp_user, smtp_password=smtp_password, frontend_url=frontend_url,
    )
