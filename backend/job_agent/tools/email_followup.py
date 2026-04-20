"""email_followup_tool — Auto-draft follow-up emails for unanswered applications.

Checks sent_emails table for emails sent N+ days ago with no follow-up yet.
Generates a polite follow-up draft and stores it in pending_emails.
Default follow-up window: 5 days.
"""
import os
import json
import asyncio
import uuid
import httpx
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from agents import function_tool
from db.database import AsyncSessionLocal
from db.models import SentEmail, PendingEmail

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
_GEMINI_MODELS = ["gemini-2.0-flash-lite", "gemini-2.0-flash"]
FOLLOWUP_DAYS  = int(os.getenv("FOLLOWUP_DAYS", "5"))


def _build_followup_prompt(
    original_subject: str,
    job_title: str,
    company: str,
    user_name: str,
    days_since: int,
) -> str:
    return (
        f"Write a short, polite follow-up email (max 80 words).\n"
        f"Context: I applied for {job_title} at {company} {days_since} days ago.\n"
        f"Original subject: {original_subject}\n"
        f"Candidate: {user_name}\n"
        f"Tone: professional, not pushy, express continued interest, ask for update.\n"
        f"Return ONLY the email body (no subject line, no extra text)."
    )


def _template_followup(job_title: str, company: str, user_name: str, days_since: int) -> str:
    return (
        f"Dear Hiring Team,\n\n"
        f"I hope this message finds you well. I wanted to follow up on my application "
        f"for the {job_title} position at {company}, submitted {days_since} days ago.\n\n"
        f"I remain very enthusiastic about this opportunity and would love to learn "
        f"more about the next steps in the process.\n\n"
        f"Thank you for your time and consideration.\n\n"
        f"Best regards,\n{user_name}"
    )


async def _call_gemini(prompt: str) -> str:
    if not GEMINI_API_KEY:
        raise ValueError("No Gemini key")
    for model in _GEMINI_MODELS:
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    resp = await client.post(
                        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                        params={"key": GEMINI_API_KEY},
                        json={"contents": [{"parts": [{"text": prompt}]}],
                              "generationConfig": {"maxOutputTokens": 200}},
                    )
                    if resp.status_code in (503, 429):
                        await asyncio.sleep(3 * (attempt + 1))
                        continue
                    resp.raise_for_status()
                    return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            except Exception:
                if attempt == 0:
                    await asyncio.sleep(1)
    raise RuntimeError("All Gemini models failed")


async def email_followup_impl(user_id: str, user_name: str = "Candidate") -> str:
    """Find sent emails that need a follow-up and draft them."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=FOLLOWUP_DAYS)

    try:
        async with AsyncSessionLocal() as session:
            # Find sent emails older than FOLLOWUP_DAYS with no existing follow-up pending
            sent_rows = (await session.execute(
                select(SentEmail).where(
                    SentEmail.user_id == uuid.UUID(user_id),
                    SentEmail.sent_at <= cutoff,
                )
            )).scalars().all()

            # Check which ones already have a follow-up draft
            existing_followups = (await session.execute(
                select(PendingEmail.job_id).where(
                    PendingEmail.user_id == uuid.UUID(user_id),
                    PendingEmail.status.in_(["pending", "sent"]),
                    PendingEmail.draft_content.like('%"followup":true%'),
                )
            )).scalars().all()
            followup_job_ids = set(str(j) for j in existing_followups if j)

            to_followup = [
                s for s in sent_rows
                if str(s.job_id) not in followup_job_ids
            ]

        drafts_created = 0
        results = []
        for sent in to_followup[:5]:  # max 5 follow-ups per run
            try:
                content = json.loads(sent.email_content)
                job_title = content.get("job_title", "the position")
                company   = content.get("company", "the company")
                orig_subj = content.get("subject", f"Re: Application for {job_title}")
                days_since = (datetime.now(timezone.utc) - sent.sent_at).days

                prompt = _build_followup_prompt(orig_subj, job_title, company, user_name, days_since)
                try:
                    body = await _call_gemini(prompt)
                except Exception:
                    body = _template_followup(job_title, company, user_name, days_since)

                draft = {
                    "success": True,
                    "subject": f"Follow-up: {orig_subj}",
                    "body":    body,
                    "recipient": sent.recipient_email,
                    "job_title": job_title,
                    "company":   company,
                    "followup":  True,
                }

                async with AsyncSessionLocal() as session:
                    async with session.begin():
                        session.add(PendingEmail(
                            id=uuid.uuid4(),
                            user_id=uuid.UUID(user_id),
                            job_id=sent.job_id,
                            draft_content=json.dumps(draft),
                            status="pending",
                        ))
                drafts_created += 1
                results.append({"job_title": job_title, "company": company, "days_since": days_since})
            except Exception as e:
                results.append({"error": str(e)})

        return json.dumps({
            "success": True,
            "followups_drafted": drafts_created,
            "details": results,
        })

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@function_tool
async def email_followup_tool(user_id: str, user_name: str = "Candidate") -> str:
    """Check for unanswered applications and draft polite follow-up emails.
    Checks sent_emails older than FOLLOWUP_DAYS (default 5).
    Creates pending follow-up drafts in pending_emails table.
    """
    return await email_followup_impl(user_id=user_id, user_name=user_name)
