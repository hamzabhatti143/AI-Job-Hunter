"""STEP 11 — Send approved email to recruiter with resume attachment."""
import os
import json
import base64
import aiosmtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from agents import function_tool


async def email_sender_impl(
    approved_email_json: str,
    validated_recruiter_email: str,
    attachment_json: str,
    smtp_host: str = "",
    smtp_port: int = 587,
    smtp_user: str = "",
    smtp_password: str = "",
) -> str:
    approved: dict = json.loads(approved_email_json)
    attachment: dict = json.loads(attachment_json)

    host = smtp_host or os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = smtp_port or int(os.getenv("SMTP_PORT", 587))
    user = smtp_user or os.getenv("SMTP_USER", "")
    password = smtp_password or os.getenv("SMTP_PASSWORD", "")
    from_email = user or os.getenv("FROM_EMAIL", "")

    msg = MIMEMultipart()
    msg["From"] = from_email
    msg["To"] = validated_recruiter_email
    msg["Subject"] = approved.get("subject", "Job Application")
    msg.attach(MIMEText(approved.get("body", ""), "plain"))

    resume_attached = False
    if attachment.get("success") and attachment.get("content_base64") and attachment.get("filename"):
        try:
            raw_bytes = base64.b64decode(attachment["content_base64"])
            filename = attachment["filename"]
            part = MIMEApplication(raw_bytes, Name=filename)
            part["Content-Disposition"] = f'attachment; filename="{filename}"'
            msg.attach(part)
            resume_attached = True
        except Exception as e:
            print(f"[WARN] Failed to attach resume: {e}")

    if not validated_recruiter_email:
        return json.dumps({
            "success": False,
            "error": "No recruiter email — cannot send",
            "resume_attached": resume_attached,
        })

    if not user or not password:
        return json.dumps({
            "success": False,
            "error": "SMTP credentials not configured",
            "resume_attached": resume_attached,
        })

    try:
        await aiosmtplib.send(
            msg,
            hostname=host,
            port=port,
            username=user,
            password=password,
            start_tls=True,
        )
        return json.dumps({
            "success": True,
            "recipient": validated_recruiter_email,
            "subject": approved.get("subject"),
            "resume_attached": resume_attached,
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e), "resume_attached": resume_attached})


@function_tool
async def email_sender_tool(
    approved_email_json: str,
    validated_recruiter_email: str,
    attachment_json: str,
    smtp_host: str = "",
    smtp_port: int = 587,
    smtp_user: str = "",
    smtp_password: str = "",
) -> str:
    """Send the approved email to recruiter with resume attached. Only call after explicit approval."""
    return await email_sender_impl(
        approved_email_json=approved_email_json,
        validated_recruiter_email=validated_recruiter_email,
        attachment_json=attachment_json,
        smtp_host=smtp_host, smtp_port=smtp_port,
        smtp_user=smtp_user, smtp_password=smtp_password,
    )
