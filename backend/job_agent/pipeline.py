"""Pipeline — Steps 1-4 (match jobs) + Step 7 (draft email content).
No email sending. Drafts are saved to DB for the user to copy and send themselves.
"""
import json
import uuid

from db.database import AsyncSessionLocal
from db.models import PendingEmail, JobMatch

from .tools.resume_parser import resume_parser_impl
from .tools.skill_extractor import skill_extractor_impl
from .tools.job_scraper import job_scraper_impl
from .tools.job_matcher import job_matcher_impl
from .tools.email_writer import email_writer_impl
from .tools.logging_tool import logging_impl
from .tools.task_manager import task_manager_impl


async def run_pipeline(
    user_id: str,
    resume_path: str,
    location: str,
    role_preference: str,
    api_key: str,
    user_email: str,
    **kwargs,  # absorb any legacy smtp/frontend_url params
) -> dict:

    async def log(event: str, detail: dict):
        await logging_impl(user_id=user_id, event_type=event, event_detail_json=json.dumps(detail))

    # STEP 1 — Parse resume
    step1 = json.loads(await resume_parser_impl(resume_path=resume_path))
    if not step1.get("success"):
        await log("resume_parse_failed", {"error": step1.get("error")})
        return {"success": False, "error": f"Resume parse failed: {step1.get('error')}"}
    resume_text = step1["resume_text"]
    await log("resume_parsed", {"file": resume_path})

    # STEP 2 — Extract skills
    step2 = json.loads(await skill_extractor_impl(resume_text=resume_text))
    skills = step2.get("skills", [])
    experience_years = step2.get("experience_years", 0)
    candidate_name = step2.get("name", "Candidate")
    candidate_email = step2.get("email") or user_email

    # Role: user input takes priority; fall back to resume-detected role
    effective_role = role_preference.strip() or step2.get("role", "")
    # Location: always use user input for searching — resume location is informational only
    effective_location = location.strip() or "Remote"
    score_location = effective_location

    await log("skills_extracted", {
        "count": len(skills),
        "experience_years": experience_years,
        "role_detected": step2.get("role", ""),
        "location_detected": step2.get("location", ""),
    })

    # STEP 3 — Scrape jobs
    step3 = json.loads(await job_scraper_impl(
        skills_json=json.dumps(skills),
        location=effective_location,
        role_preference=effective_role,
    ))
    scraped_jobs = step3.get("jobs", [])
    await log("jobs_scraped", {"count": len(scraped_jobs)})

    if not scraped_jobs:
        return {
            "success": True,
            "output": "No jobs found for your criteria. Try a broader location or role preference.",
            "matched_jobs": 0,
            "drafts": 0,
        }

    # STEP 4 — Match jobs (saves to DB, returns db_job_id per job)
    step4 = json.loads(await job_matcher_impl(
        jobs_json=json.dumps(scraped_jobs),
        skills_json=json.dumps(skills),
        experience_years=experience_years,
        location=score_location,
        user_id=user_id,
        role_preference=effective_role,
    ))
    matched_jobs = step4.get("matched_jobs", [])
    await log("jobs_matched", {"total_matched": len(matched_jobs)})

    if not matched_jobs:
        return {
            "success": True,
            "output": (
                f"Found {len(scraped_jobs)} jobs but none scored 65%+ for your role and skills. "
                "Tips: use a specific role (e.g. 'Frontend Developer React'), "
                "make sure your resume lists specific technologies, and try 'Remote' as location."
            ),
            "matched_jobs": 0,
            "drafts": 0,
        }

    # STEP 7 — Draft application emails for top 3 matched jobs
    draft_count = 0
    for job in matched_jobs[:3]:
        job_title = job.get("title", "")
        company = job.get("company", "")
        db_job_id = job.get("db_job_id", "")

        try:
            step7 = json.loads(await email_writer_impl(
                job_json=json.dumps({"title": job_title, "company": company, "url": job.get("url", "")}),
                skills_json=json.dumps(skills),
                user_name=candidate_name,
                user_email=candidate_email,
                api_key=api_key,
                recruiter_email="",
            ))
            if not step7.get("success"):
                await log("draft_write_failed", {"job": job_title, "error": step7.get("error")})
                continue

            # Save draft to DB
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    session.add(PendingEmail(
                        id=uuid.uuid4(),
                        user_id=uuid.UUID(user_id),
                        job_id=uuid.UUID(db_job_id) if db_job_id else None,
                        draft_content=json.dumps(step7),
                        status="pending",
                    ))
            await log("draft_created", {"job": job_title, "company": company})
            draft_count += 1

        except Exception as e:
            await log("draft_error", {"job": job_title, "error": str(e)})

    await log("pipeline_complete", {"matched": len(matched_jobs), "drafts": draft_count})
    await task_manager_impl(user_id=user_id)

    return {
        "success": True,
        "output": (
            f"Done! Matched {len(matched_jobs)} jobs. "
            f"Drafted {draft_count} application email(s) — go to Application Drafts to copy and send."
        ),
        "matched_jobs": len(matched_jobs),
        "drafts": draft_count,
        "detected_role": step2.get("role", ""),
        "detected_location": step2.get("location", ""),
    }
