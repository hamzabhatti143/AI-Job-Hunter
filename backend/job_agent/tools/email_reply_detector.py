"""email_reply_detector_tool — Monitor user inbox for recruiter replies via IMAP.

Connects to the user's mail account (credentials from User.smtp_* fields),
scans the last 50 unread messages, and returns those from addresses we
previously sent job applications to.

Supports Gmail and any standard IMAP-SSL server.
"""
import email
import imaplib
import json
import uuid
from email.header import decode_header

from sqlalchemy import select
from agents import function_tool

from db.database import AsyncSessionLocal
from db.models import SentEmail, User


def _decode_header_val(value: str | None) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    result = []
    for chunk, charset in parts:
        if isinstance(chunk, bytes):
            result.append(chunk.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(str(chunk))
    return " ".join(result)


def _infer_imap_host(smtp_host: str) -> str:
    h = smtp_host.lower()
    if "gmail" in h:
        return "imap.gmail.com"
    if "outlook" in h or "hotmail" in h or "live" in h:
        return "imap-mail.outlook.com"
    if "yahoo" in h:
        return "imap.mail.yahoo.com"
    # Generic: swap "smtp." → "imap."
    return smtp_host.replace("smtp.", "imap.")


async def email_reply_detector_impl(user_id: str) -> str:
    uid = uuid.UUID(user_id)

    try:
        async with AsyncSessionLocal() as session:
            user = (await session.execute(
                select(User).where(User.id == uid)
            )).scalar_one_or_none()

            if not user:
                return json.dumps({"success": False, "error": "User not found."})

            if not (user.smtp_host and user.smtp_user and user.smtp_password):
                return json.dumps({
                    "success": False,
                    "error": "IMAP credentials not configured — add SMTP settings in Settings.",
                })

            sent_rows = (await session.execute(
                select(SentEmail).where(SentEmail.user_id == uid)
            )).scalars().all()

        recruiter_addresses = {row.recipient_email.lower() for row in sent_rows}
        if not recruiter_addresses:
            return json.dumps({
                "success": True,
                "replies_found": [],
                "message": "No sent applications to check replies for.",
            })

        imap_host = _infer_imap_host(user.smtp_host)

        replies: list[dict] = []
        try:
            conn = imaplib.IMAP4_SSL(imap_host, 993)
            conn.login(user.smtp_user, user.smtp_password)
            conn.select("INBOX")
            _, data = conn.search(None, "UNSEEN")
            mail_ids = (data[0] or b"").split()

            for mid in mail_ids[-50:]:  # cap at last 50 unread
                _, msg_data = conn.fetch(mid, "(RFC822)")
                if not msg_data or not msg_data[0]:
                    continue
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)

                from_hdr  = _decode_header_val(msg.get("From", ""))
                from_lower = from_hdr.lower()

                if any(addr in from_lower for addr in recruiter_addresses):
                    subject = _decode_header_val(msg.get("Subject", ""))
                    replies.append({
                        "from":    from_hdr,
                        "subject": subject,
                        "date":    msg.get("Date", ""),
                    })

            conn.logout()
        except imaplib.IMAP4.error as exc:
            return json.dumps({"success": False, "error": f"IMAP error: {exc}"})

        return json.dumps({
            "success":       True,
            "replies_found": replies,
            "count":         len(replies),
        })

    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)})


@function_tool
async def email_reply_detector_tool(user_id: str) -> str:
    """Scan the user's inbox for recruiter replies to sent job applications.

    Matches incoming senders against addresses in the sent_emails table.
    Returns list of reply emails with from/subject/date fields.
    """
    return await email_reply_detector_impl(user_id=user_id)
