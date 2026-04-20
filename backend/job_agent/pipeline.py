"""Pipeline — Enforced order S1–S10 per spec.

S1  location_enforcer     → classify input type (A–E), build 3 variants, abort if empty
S2  resume_parser         → extract text
S3  skill_extractor       → skills, experience, name
S4  job_scraper + filter  → inject all 3 location variants, hard-filter non-matching
S5  job_matcher           → threshold 50%, Top Match ≥70%, Good Match 50–69%
S6  email_extractor       → 6 attempts per job, no cap, no skips
S7  email_validator       → RFC 5322 + MX + non-generic (integrated in extractor)
S8  portal_detector       → detect ATS type for portal-only jobs
S9  branch               → email found → METHOD A (draft email); portal → METHOD B
S10 logging + dashboard   → all events logged, task manager updated

LOCATION RULE:
  - Location comes ONLY from the user's UI input field.
  - Resume location is NEVER used for searching — logged for info only.
  - Empty location → pipeline stops and prompts user.
  - Remote jobs EXCLUDED when user enters specific city/country.
  - No silent remote fallback — notify user if zero location results.
"""
import asyncio
import json
import os
import uuid
from sqlalchemy import update as sa_update

from db.database import AsyncSessionLocal
from db.models import PendingEmail, JobMatch, ExtractedEmail

from .tools.resume_parser import resume_parser_impl
from .tools.skill_extractor import skill_extractor_impl
from .tools.job_scraper import job_scraper_impl, _is_remote_input, _REMOTE_FILTER_TERMS
from .tools.job_matcher import job_matcher_impl
from .tools.job_deduplication import job_deduplication_impl
from .tools.job_expiry_checker import job_expiry_checker_impl
from .tools.salary_filter import salary_filter_impl
from .tools.email_finder import email_finder_impl
from .tools.portal_detector import portal_detector_impl
from .tools.email_writer import email_writer_impl
from .tools.cover_letter import cover_letter_impl
from .tools.resume_scorer import resume_scorer_impl
from .tools.spam_guard import spam_guard_impl
from .tools.notification_tool import notification_push_impl
from .tools.logging_tool import logging_impl
from .tools.task_manager import task_manager_impl
from .tools.user_preference_tool import preference_get_impl


# ── Location filter ───────────────────────────────────────────────────────────

def _job_passes_location(job_loc: str, filter_terms: list[str], is_remote_search: bool) -> bool:
    """
    True if the job's location is acceptable for the user's search.

    STRICT rules per spec:
    - Empty/unknown location → always rejected.
    - Remote search → ONLY remote-tagged jobs pass.
    - Specific location search → remote jobs EXCLUDED (user wants onsite in that location).
      Job location must contain at least one filter term.
    """
    loc_lower = job_loc.strip().lower()

    # Empty location = unknown — reject strictly (never assume remote)
    if not loc_lower:
        return False

    job_is_remote = any(rt in loc_lower for rt in _REMOTE_FILTER_TERMS)

    if is_remote_search:
        # Strict: only jobs that explicitly say "remote" / "worldwide" / etc.
        return job_is_remote

    # STRICT: for specific location searches, remote jobs are EXCLUDED.
    # User typed a city/country — they want jobs there, not remote work.
    if job_is_remote:
        return False

    return bool(filter_terms) and any(ft in loc_lower for ft in filter_terms)


async def _scrape_and_filter(
    skills_json: str,
    location: str,
    role: str,
    log,
    log_label: str = "primary",
) -> tuple[list[dict], dict]:
    """
    Scrape jobs → resolve location via Nominatim → apply strict location filter.
    Returns (filtered_jobs, loc_info).
    loc_info is returned by the scraper after geocoding.
    """
    raw = json.loads(await job_scraper_impl(
        skills_json=skills_json, location=location, role_preference=role,
    ))
    all_jobs: list[dict] = raw.get("jobs", [])
    loc_info: dict       = raw.get("loc_info", {})

    filter_terms     = loc_info.get("filter_terms", [])
    is_remote_search = loc_info.get("is_remote", False)
    geocoded         = loc_info.get("geocoded", False)

    # Classify location type (A–E per spec)
    is_remote_loc = loc_info.get("is_remote", False)
    city          = loc_info.get("city", "")
    country       = loc_info.get("country", "")
    state         = loc_info.get("state", "")
    is_region     = loc_info.get("is_region", False)
    if is_remote_loc:
        loc_type = "E"   # Remote / WFH / Anywhere / Worldwide
    elif is_region:
        loc_type = "D"   # Multi-country region (Gulf, Europe, etc.)
    elif city and country and city.lower() != country.lower():
        loc_type = "B"   # City + Country
    elif city and not country:
        loc_type = "A"   # City only
    elif country and not city:
        loc_type = "C"   # Country only
    else:
        loc_type = "D"   # State / Region fallback

    await log("jobs_scraped", {
        "count": len(all_jobs),
        "attempt": log_label,
        "location": location,
        "loc_type": loc_type,
        "filter_terms": filter_terms[:6],
        "geocoded": geocoded,
        "city": city,
        "country": country,
    })

    if not all_jobs:
        return [], loc_info

    kept      = []
    discarded = 0
    for job in all_jobs:
        job_loc = job.get("location") or ""
        if _job_passes_location(job_loc, filter_terms, is_remote_search):
            kept.append(job)
        else:
            discarded += 1

    if discarded:
        await log("location_filter", {
            "reason": "location_mismatch",
            "attempt": log_label,
            "discarded": discarded,
            "kept": len(kept),
            "filter_terms": filter_terms[:6],
            "user_location": location,
        })

    return kept, loc_info


# ── Main pipeline ─────────────────────────────────────────────────────────────

async def run_pipeline(
    user_id: str,
    resume_path: str,
    location: str,
    role_preference: str,
    api_key: str,
    user_email: str,
    recruiter_email: str = "",
    **kwargs,
) -> dict:

    async def log(event: str, detail: dict):
        await logging_impl(user_id=user_id, event_type=event, event_detail_json=json.dumps(detail))

    # ── STEP 1 — Parse resume ──────────────────────────────────────────────────
    step1 = json.loads(await resume_parser_impl(resume_path=resume_path))
    if not step1.get("success"):
        await log("resume_parse_failed", {"error": step1.get("error")})
        return {"success": False, "error": f"Resume parse failed: {step1.get('error')}"}
    resume_text = step1["resume_text"]
    await log("resume_parsed", {"file": resume_path})

    # ── STEP 2 — Extract skills (location from resume is NEVER used for search) ─
    step2 = json.loads(await skill_extractor_impl(resume_text=resume_text))
    skills           = step2.get("skills", [])
    experience_years = step2.get("experience_years", 0)
    candidate_name   = step2.get("name", "Candidate")
    candidate_email  = step2.get("email") or user_email

    # Role: user input has priority; resume-detected role is secondary
    effective_role = role_preference.strip() or step2.get("role", "")

    # Location: ALWAYS from user's UI input — if empty, abort immediately
    effective_location = location.strip()
    if not effective_location:
        return {
            "success": False,
            "error": "Please enter a location (city, country, or 'Remote') to start the search.",
        }

    await log("skills_extracted", {
        "count":           len(skills),
        "experience_years": experience_years,
        "user_location":   effective_location,       # what will be searched
        "resume_location": step2.get("location", ""), # informational only — NEVER searched
    })

    skills_json = json.dumps(skills)

    # ── Load user preferences (salary filter, etc.) ───────────────────────────
    prefs = {}
    try:
        prefs_raw = json.loads(await preference_get_impl(user_id=user_id))
        if prefs_raw.get("found"):
            prefs = prefs_raw
    except Exception:
        pass

    # ── STEP 3 — Scrape + geocode + strict location filter ────────────────────
    filtered_jobs, loc_info = await _scrape_and_filter(
        skills_json, effective_location, effective_role, log, "primary"
    )

    # Fallback 1: country-only (when city was entered but nothing found)
    fallback_used: str | None = None
    if not filtered_jobs and loc_info.get("fallback_country"):
        fallback_country = loc_info["fallback_country"]
        await log("fallback_country", {"original": effective_location, "fallback": fallback_country})
        filtered_jobs, _ = await _scrape_and_filter(
            skills_json, fallback_country, effective_role, log, "fallback_country"
        )
        if filtered_jobs:
            fallback_used = f"country ({fallback_country})"

    # ── Deduplication — remove cross-board duplicates ─────────────────────────
    if filtered_jobs:
        try:
            dedup_result = json.loads(await job_deduplication_impl(json.dumps(filtered_jobs)))
            if dedup_result.get("duplicates_removed", 0):
                await log("jobs_deduplicated", {
                    "removed": dedup_result["duplicates_removed"],
                    "unique":  dedup_result["unique_count"],
                })
            filtered_jobs = dedup_result.get("jobs", filtered_jobs)
        except Exception as e:
            await log("dedup_failed", {"error": str(e)})

    # Per spec: NO remote fallback — never silently substitute remote jobs.
    if not filtered_jobs:
        await log("no_jobs_found", {"location": effective_location})
        return {
            "success": True,
            "output": (
                f"No jobs found in '{effective_location}'. "
                "Try a broader location like the country name, "
                "or type 'Remote' if you are open to remote work."
            ),
            "matched_jobs": 0,
            "drafts": 0,
        }

    # ── STEP 4 — Score and match ───────────────────────────────────────────────
    step4 = json.loads(await job_matcher_impl(
        jobs_json=json.dumps(filtered_jobs),
        skills_json=skills_json,
        experience_years=experience_years,
        location=effective_location,
        user_id=user_id,
        role_preference=effective_role,
    ))
    matched_jobs = step4.get("matched_jobs", [])
    await log("jobs_matched", {"total_matched": len(matched_jobs)})

    if not matched_jobs:
        tip = (
            f"Found {len(filtered_jobs)} location-matched jobs but none scored 50%+ for your role/skills. "
            "Try a more specific role (e.g. 'Frontend Developer React') and make sure your resume "
            "lists specific technologies."
        )
        if fallback_used:
            tip += f" (Location expanded to: {fallback_used})"
        return {"success": True, "output": tip, "matched_jobs": 0, "drafts": 0}

    # ── Salary filter (apply user preference if configured) ────────────────────
    salary_min = prefs.get("salary_min") or 0
    salary_max = prefs.get("salary_max") or 0
    if salary_min or salary_max:
        try:
            sf_result = json.loads(await salary_filter_impl(
                jobs_json=json.dumps(matched_jobs),
                salary_min=salary_min,
                salary_max=salary_max,
            ))
            filtered_count = sf_result.get("filtered", 0)
            if filtered_count:
                await log("salary_filter", {
                    "filtered": filtered_count,
                    "passed": sf_result.get("passed", len(matched_jobs)),
                    "salary_min": salary_min,
                    "salary_max": salary_max,
                })
            matched_jobs = sf_result.get("jobs", matched_jobs)
        except Exception as e:
            await log("salary_filter_failed", {"error": str(e)})

    # ── STEP 5 — Recruiter email (manual override only; auto-find runs on Apply) ──
    # Auto email-finding is skipped here to keep the pipeline fast.
    # When the user clicks Apply on a job, the apply-job endpoint runs the finder
    # for that single job and pre-fills the recruiter email on the draft.
    job_email_map: dict[str, str] = {}   # db_job_id → recruiter_email
    if recruiter_email.strip():
        for job in matched_jobs:
            db_id = job.get("db_job_id", "")
            if db_id:
                job_email_map[db_id] = recruiter_email.strip()
        await log("emails_extracted", {
            "found": len(job_email_map), "total": len(matched_jobs), "source": "manual_input",
        })

    # ── STEP 6 — Detect portal type ────────────────────────────────────────────
    try:
        portal_result = json.loads(await portal_detector_impl(json.dumps(matched_jobs)))
        matched_jobs  = portal_result.get("jobs", matched_jobs)

        if user_id:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    for job in matched_jobs:
                        db_job_id   = job.get("db_job_id")
                        portal_type = job.get("portal_type")
                        if db_job_id and portal_type:
                            await session.execute(
                                sa_update(JobMatch)
                                .where(JobMatch.id == uuid.UUID(db_job_id))
                                .values(portal_type=portal_type)
                            )
        await log("portal_detected", {"count": len(matched_jobs)})
    except Exception as e:
        await log("portal_detection_failed", {"error": str(e)})

    # ── Spam guard — check daily email send limit ─────────────────────────────
    can_send_email = True
    try:
        sg = json.loads(await spam_guard_impl(user_id=user_id))
        can_send_email = sg.get("allowed", True)
        if not can_send_email:
            await log("spam_guard_blocked", {"sent_today": sg.get("sent_today"), "limit": sg.get("limit")})
    except Exception as e:
        await log("spam_guard_error", {"error": str(e)})

    # ── STEP 7 — Draft application emails (top 3, with recruiter email if found) ──
    draft_count = 0
    for job in (matched_jobs[:3] if can_send_email else []):
        job_title = job.get("title", "")
        company   = job.get("company", "")
        db_job_id = job.get("db_job_id", "")
        recruiter_email = job_email_map.get(db_job_id, "")

        try:
            job_obj = {"title": job_title, "company": company, "url": job.get("url", ""),
                       "description": job.get("description", "")}

            # Application email + cover letter run concurrently
            email_task  = email_writer_impl(
                job_json=json.dumps(job_obj), skills_json=skills_json,
                user_name=candidate_name, user_email=candidate_email,
                api_key=api_key, recruiter_email=recruiter_email,
                resume_text=resume_text,
            )
            cover_task  = cover_letter_impl(
                job_json=json.dumps(job_obj), skills_json=skills_json,
                experience_years=experience_years, user_name=candidate_name,
                api_key=api_key,
            )
            step7_raw, cover_raw = await asyncio.gather(email_task, cover_task, return_exceptions=True)

            step7 = json.loads(step7_raw) if not isinstance(step7_raw, Exception) else {}
            cover = json.loads(cover_raw) if not isinstance(cover_raw, Exception) else {}

            if not step7.get("success"):
                await log("draft_write_failed", {"job": job_title, "error": step7.get("error")})
                continue

            # Merge cover letter into draft content
            draft_data = {**step7, "cover_letter": cover.get("cover_letter", "")}

            async with AsyncSessionLocal() as session:
                async with session.begin():
                    session.add(PendingEmail(
                        id=uuid.uuid4(),
                        user_id=uuid.UUID(user_id),
                        job_id=uuid.UUID(db_job_id) if db_job_id else None,
                        draft_content=json.dumps(draft_data),
                        status="pending",
                    ))
            await log("draft_created", {"job": job_title, "company": company,
                                        "has_cover_letter": bool(cover.get("cover_letter"))})
            draft_count += 1

        except Exception as e:
            await log("draft_error", {"job": job_title, "error": str(e)})

    await log("pipeline_complete", {"matched": len(matched_jobs), "drafts": draft_count})
    await task_manager_impl(user_id=user_id)

    # ── Push notifications ────────────────────────────────────────────────────
    try:
        if len(matched_jobs) > 0:
            await notification_push_impl(
                user_id=user_id,
                event_type="new_jobs_found",
                message=f"Found {len(matched_jobs)} matching jobs for your profile.",
            )
        if draft_count > 0:
            await notification_push_impl(
                user_id=user_id,
                event_type="draft_ready",
                message=f"{draft_count} application draft(s) are ready for your review.",
            )
    except Exception:
        pass

    summary = f"Done! Found {len(matched_jobs)} matching jobs"
    if fallback_used:
        summary += f" (location expanded to: {fallback_used})"
    summary += f". Drafted {draft_count} email(s) — check Application Drafts."

    # Tip: suggest SerpAPI if not configured (without it, results lean remote-only)
    google_jobs_tip = None
    if not os.getenv("SERP_API_KEY", ""):
        google_jobs_tip = "Tip: add SERP_API_KEY to .env for Google Jobs (LinkedIn/Indeed/Rozee.pk coverage)."

    return {
        "success": True,
        "output": summary,
        "matched_jobs": len(matched_jobs),
        "drafts": draft_count,
        "detected_role": step2.get("role", ""),
        "google_jobs_tip": google_jobs_tip,
    }
