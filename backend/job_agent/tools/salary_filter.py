"""salary_filter_tool — Filter jobs by salary range preference.

Extracts salary from job listing text (title + description + explicit salary field).
Jobs with no detectable salary are kept (never silently filtered when unknown).
Jobs whose extracted range falls outside the user's preference are removed.
"""
import json
import re
from agents import function_tool

_PATTERNS = [
    # "$X – $Y k/yr"  or  "$X,000 - $Y,000"
    r"\$\s*(\d[\d,]*)\s*k?\s*[-–—]\s*\$?\s*(\d[\d,]*)\s*k?",
    # "X – Y USD"  or  "X,000 - Y,000 USD/GBP/EUR"
    r"(\d[\d,]+)\s*k?\s*[-–—]\s*(\d[\d,]+)\s*k?\s*(?:usd|gbp|eur|pkr)?",
    # "up to $X k"
    r"up\s+to\s+\$?\s*(\d[\d,]+)\s*(k)?",
    # "from $X"
    r"from\s+\$?\s*(\d[\d,]+)\s*(k)?",
    # single "$X k" or "$X,000"
    r"\$\s*(\d[\d,]+)\s*(k)",
]


def _clean(val: str) -> int:
    return int(val.replace(",", ""))


def _extract_salary(text: str) -> tuple[int | None, int | None]:
    """Return (min_annual, max_annual) in USD integers, or (None, None)."""
    if not text:
        return None, None

    text_lower = text.lower()

    for pat in _PATTERNS:
        m = re.search(pat, text_lower)
        if not m:
            continue
        groups = [g for g in m.groups() if g is not None]
        nums: list[int] = []
        for g in groups:
            if re.fullmatch(r"[\d,]+", g):
                n = _clean(g)
                # Detect "k" shorthand from the surrounding match context
                span = text_lower[m.start():m.end()]
                if n < 1000 and "k" in span:
                    n *= 1000
                nums.append(n)

        if len(nums) >= 2:
            return min(nums), max(nums)
        if len(nums) == 1:
            return nums[0], None

    return None, None


async def salary_filter_impl(
    jobs_json: str,
    salary_min: int = 0,
    salary_max: int = 0,
) -> str:
    jobs = json.loads(jobs_json) if isinstance(jobs_json, str) else jobs_json
    if isinstance(jobs, dict):
        jobs = jobs.get("jobs", [])

    # No filter configured → return all unchanged
    if not salary_min and not salary_max:
        return json.dumps({"success": True, "jobs": jobs, "filtered": 0, "message": "No salary filter configured."})

    passed: list[dict] = []
    filtered_count = 0

    for job in jobs:
        text = " ".join(filter(None, [
            job.get("description") or "",
            job.get("title") or "",
            job.get("salary") or "",
        ]))
        job_min, job_max = _extract_salary(text)

        # Unknown salary → keep (never penalise jobs that don't list salary)
        if job_min is None and job_max is None:
            passed.append(job)
            continue

        user_lo = salary_min or 0
        user_hi = salary_max or 10_000_000
        job_lo  = job_min or 0
        job_hi  = job_max or job_lo

        # Filter only when ranges are completely disjoint
        if job_hi < user_lo or (user_hi and job_lo > user_hi):
            filtered_count += 1
        else:
            passed.append(job)

    return json.dumps({
        "success":        True,
        "jobs":           passed,
        "original_count": len(jobs),
        "passed":         len(passed),
        "filtered":       filtered_count,
    })


@function_tool
async def salary_filter_tool(jobs_json: str, salary_min: int = 0, salary_max: int = 0) -> str:
    """Filter job listings to those matching the user's salary range.

    Jobs with no salary info are kept (unknown ≠ disqualified).
    salary_min / salary_max: annual USD integers; 0 means no bound.
    """
    return await salary_filter_impl(
        jobs_json=jobs_json, salary_min=salary_min, salary_max=salary_max
    )
