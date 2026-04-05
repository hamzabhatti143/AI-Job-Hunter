"""STEP 6 — Validate email format, domain, and MX records."""
import re
import json
import asyncio
import dns.resolver
from agents import function_tool

RFC5322_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


async def _check_mx(domain: str) -> bool:
    try:
        loop = asyncio.get_event_loop()
        answers = await loop.run_in_executor(None, dns.resolver.resolve, domain, "MX")
        return len(answers) > 0
    except Exception:
        return False


async def email_validator_impl(email_results_json: str) -> str:
    raw = json.loads(email_results_json)
    email_results = raw.get("email_results", []) if isinstance(raw, dict) else raw

    validated: list = []
    discarded: list = []

    async def validate_one(email: str, meta: dict) -> None:
        if not RFC5322_RE.match(email):
            discarded.append({"email": email, "reason": "invalid_format", **meta})
            return
        domain = email.split("@")[1]
        if not await _check_mx(domain):
            discarded.append({"email": email, "reason": "no_mx_record", **meta})
            return
        validated.append({"email": email, "is_valid": True, **meta})

    tasks = []
    for result in email_results:
        if not isinstance(result, dict):
            continue
        meta = {
            "job_title": result.get("job_title"),
            "company": result.get("company"),
            "job_url": result.get("job_url"),
            "db_job_id": result.get("db_job_id", ""),
        }
        for email in result.get("emails", []):
            tasks.append(validate_one(email, meta))

    if tasks:
        await asyncio.gather(*tasks)

    # If no recruiter emails found, still continue pipeline with placeholders
    if not validated and email_results:
        for result in email_results[:5]:
            if not isinstance(result, dict):
                continue
            validated.append({
                "email": "",
                "is_valid": False,
                "job_title": result.get("job_title"),
                "company": result.get("company"),
                "job_url": result.get("job_url"),
                "db_job_id": result.get("db_job_id", ""),
                "note": "no_recruiter_email_found",
            })

    return json.dumps({"success": True, "validated_emails": validated, "discarded_emails": discarded})


@function_tool
async def email_validator_tool(email_results_json: str) -> str:
    """Validate each extracted email: RFC5322 format check + MX record lookup.
    email_results_json: JSON array of objects with emails, job_title, company, job_url, db_job_id.
    Returns JSON with validated_emails and discarded_emails arrays.
    """
    return await email_validator_impl(email_results_json=email_results_json)
