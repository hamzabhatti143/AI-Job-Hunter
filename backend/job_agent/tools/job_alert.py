"""job_alert_tool — Monitor sources for new matching jobs on a schedule.

Checks the last pipeline_complete event in the activity log.
Returns run_due=True if the configured interval has elapsed.
Actual re-run is triggered via the API endpoint; this tool only decides timing.

Interval is controlled by JOB_ALERT_INTERVAL_HOURS env var (default 12 hrs).
"""
import json
import os
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from agents import function_tool

from db.database import AsyncSessionLocal
from db.models import ActivityLog

DEFAULT_INTERVAL_HOURS = int(os.getenv("JOB_ALERT_INTERVAL_HOURS", "12"))


async def job_alert_check_impl(user_id: str) -> str:
    """Return whether a new pipeline run is due based on alert interval."""
    uid = uuid.UUID(user_id)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=DEFAULT_INTERVAL_HOURS)

    try:
        async with AsyncSessionLocal() as session:
            last_run = (await session.execute(
                select(ActivityLog)
                .where(
                    ActivityLog.user_id == uid,
                    ActivityLog.event_type == "pipeline_complete",
                )
                .order_by(ActivityLog.logged_at.desc())
                .limit(1)
            )).scalar_one_or_none()

        if not last_run or last_run.logged_at < cutoff:
            return json.dumps({
                "success":         True,
                "run_due":         True,
                "last_run":        last_run.logged_at.isoformat() if last_run else None,
                "interval_hours":  DEFAULT_INTERVAL_HOURS,
                "message":         "Job alert: a new pipeline run is due.",
            })

        next_run = last_run.logged_at + timedelta(hours=DEFAULT_INTERVAL_HOURS)
        return json.dumps({
            "success":        True,
            "run_due":        False,
            "last_run":       last_run.logged_at.isoformat(),
            "next_run":       next_run.isoformat(),
            "interval_hours": DEFAULT_INTERVAL_HOURS,
            "message":        f"Next alert check due at {next_run.strftime('%Y-%m-%d %H:%M UTC')}.",
        })

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@function_tool
async def job_alert_tool(user_id: str) -> str:
    """Check whether a new scheduled job-search run is due.

    Returns run_due=True when JOB_ALERT_INTERVAL_HOURS have elapsed since
    the last pipeline_complete event. The caller should trigger run_pipeline().
    """
    return await job_alert_check_impl(user_id=user_id)
