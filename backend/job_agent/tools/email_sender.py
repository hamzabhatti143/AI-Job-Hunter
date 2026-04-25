"""STEP 11 — Send approved email to recruiter with resume attachment via Gmail API."""
import os
import json
import base64
import uuid
import httpx
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders as email_encoders
from datetime import datetime, timezone, timedelta
from agents import function_tool


async def _get_gmail_token(user_id: str) -> tuple[str, str]:
    """Return (access_token, user_email) for user_id, refreshing if needed."""
    from db.database import AsyncSessionLocal
    from db.models import User
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.id == uuid.UUID(user_id)))).scalar_one_or_none()
        if not user or not user.gmail_refresh_token:
            raise ValueError("Gmail not connected — please connect Gmail in Settings")

        now = datetime.now(timezone.utc)
        needs_refresh = (
            not user.gmail_access_token
            or not user.gmail_token_expiry
            or user.gmail_token_expiry <= now + timedelta(minutes=2)
        )
        if needs_refresh:
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
            user.gmail_token_expiry = now + timedelta(seconds=tokens.get("expires_in", 3600))
            db.add(user)
            await db.commit()

        return user.gmail_access_token, user.email


async def email_sender_impl(
    approved_email_json: str,
    validated_recruiter_email: str,
    attachment_json: str,
    user_id: str = "",
    smtp_host: str = "",
    smtp_port: int = 587,
    smtp_user: str = "",
    smtp_password: str = "",
) -> str:
    approved: dict = json.loads(approved_email_json)
    attachment: dict = json.loads(attachment_json)

    if not validated_recruiter_email:
        return json.dumps({"success": False, "error": "No recruiter email — cannot send"})

    if not user_id:
        return json.dumps({"success": False, "error": "user_id is required to send via Gmail"})

    try:
        access_token, from_email = await _get_gmail_token(user_id)
    except ValueError as e:
        return json.dumps({"success": False, "error": str(e)})

    msg = MIMEMultipart()
    msg["To"]      = validated_recruiter_email
    msg["From"]    = from_email
    msg["Subject"] = approved.get("subject", "Job Application")
    msg.attach(MIMEText(approved.get("body", ""), "plain"))

    resume_attached = False
    if attachment.get("success") and attachment.get("content_base64") and attachment.get("filename"):
        try:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(base64.b64decode(attachment["content_base64"]))
            email_encoders.encode_base64(part)
            part.add_header("Content-Disposition", "attachment", filename=attachment["filename"])
            msg.attach(part)
            resume_attached = True
        except Exception as e:
            print(f"[WARN] Failed to attach resume: {e}")

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                headers={"Authorization": f"Bearer {access_token}"},
                json={"raw": raw},
                timeout=15,
            )
            if r.status_code >= 400:
                return json.dumps({"success": False, "error": f"Gmail API error {r.status_code}: {r.text}"})

        return json.dumps({
            "success":         True,
            "recipient":       validated_recruiter_email,
            "subject":         approved.get("subject"),
            "resume_attached": resume_attached,
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e), "resume_attached": resume_attached})


@function_tool
async def email_sender_tool(
    approved_email_json: str,
    validated_recruiter_email: str,
    attachment_json: str,
    user_id: str = "",
    smtp_host: str = "",
    smtp_port: int = 587,
    smtp_user: str = "",
    smtp_password: str = "",
) -> str:
    """Send the approved email to recruiter with resume attached via Gmail API. Only call after explicit approval."""
    return await email_sender_impl(
        approved_email_json=approved_email_json,
        validated_recruiter_email=validated_recruiter_email,
        attachment_json=attachment_json,
        user_id=user_id,
        smtp_host=smtp_host, smtp_port=smtp_port,
        smtp_user=smtp_user, smtp_password=smtp_password,
    )
