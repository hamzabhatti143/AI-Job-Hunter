"""analytics_tool — Application performance statistics.

Queries DB tables to produce per-user analytics:
  - Total jobs matched / applied
  - Emails sent today / this week / total
  - Follow-ups sent
  - Applications by day (last 14 days)
  - Top sources that produced matches
  - Match score distribution
"""
import json
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func
from db.database import AsyncSessionLocal
from db.models import JobMatch, SentEmail, PendingEmail, ActivityLog


async def analytics_impl(user_id: str) -> str:
    uid = uuid.UUID(user_id)
    now = datetime.now(timezone.utc)
    today_start  = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start   = today_start - timedelta(days=7)
    two_weeks_ago = today_start - timedelta(days=14)

    try:
        async with AsyncSessionLocal() as session:

            # ── Job match stats ──────────────────────────────────────────
            all_jobs = (await session.execute(
                select(JobMatch).where(JobMatch.user_id == uid)
            )).scalars().all()

            total_matched  = len(all_jobs)
            total_applied  = sum(1 for j in all_jobs if j.status == "applied")
            top_match_count = sum(1 for j in all_jobs if j.match_tier == "Top Match")
            avg_score = (
                round(sum(float(j.match_score or 0) for j in all_jobs) / total_matched, 1)
                if total_matched else 0
            )

            # Source distribution
            source_counts: dict[str, int] = {}
            for j in all_jobs:
                s = j.source or "unknown"
                source_counts[s] = source_counts.get(s, 0) + 1

            # ── Email stats ───────────────────────────────────────────────
            all_sent = (await session.execute(
                select(SentEmail).where(SentEmail.user_id == uid)
            )).scalars().all()

            emails_total      = len(all_sent)
            emails_today      = sum(1 for e in all_sent if e.sent_at >= today_start)
            emails_this_week  = sum(1 for e in all_sent if e.sent_at >= week_start)
            followups_sent    = sum(
                1 for e in all_sent
                if "followup" in (e.email_content or "") and '"followup": true' in (e.email_content or "")
            )

            # ── Pending drafts ────────────────────────────────────────────
            drafts_pending = (await session.execute(
                select(func.count(PendingEmail.id)).where(
                    PendingEmail.user_id == uid,
                    PendingEmail.status == "pending",
                )
            )).scalar() or 0

            # ── Applications by day (last 14 days) ──────────────────────
            daily: dict[str, int] = {}
            for e in all_sent:
                day = e.sent_at.strftime("%Y-%m-%d")
                daily[day] = daily.get(day, 0) + 1

            # Fill in missing days with 0
            applications_by_day = []
            for i in range(14):
                day = (today_start - timedelta(days=13 - i)).strftime("%Y-%m-%d")
                applications_by_day.append({"date": day, "count": daily.get(day, 0)})

        return json.dumps({
            "success": True,
            "jobs": {
                "total_matched":   total_matched,
                "total_applied":   total_applied,
                "top_matches":     top_match_count,
                "avg_match_score": avg_score,
                "by_source":       source_counts,
            },
            "emails": {
                "total_sent":      emails_total,
                "sent_today":      emails_today,
                "sent_this_week":  emails_this_week,
                "followups_sent":  followups_sent,
                "drafts_pending":  int(drafts_pending),
            },
            "applications_by_day": applications_by_day,
        })

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})
