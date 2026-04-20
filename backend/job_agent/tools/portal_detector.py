"""Portal detector — identify ATS/job board type from a job URL."""
import re
from agents import function_tool

# (portal_name, url_patterns)
PORTAL_PATTERNS = [
    ("Workday",         [r"myworkdayjobs\.com", r"workday\.com/en-us/apps/talent"]),
    ("Greenhouse",      [r"boards\.greenhouse\.io", r"app\.greenhouse\.io"]),
    ("Lever",           [r"jobs\.lever\.co", r"lever\.co/[^/]+/jobs"]),
    ("Taleo",           [r"taleo\.net", r"tbe\.taleo\.net"]),
    ("BambooHR",        [r"bamboohr\.com/jobs", r"bamboohr\.com/careers"]),
    ("SmartRecruiters", [r"jobs\.smartrecruiters\.com", r"smartrecruiters\.com/jobs"]),
    ("iCIMS",           [r"icims\.com", r"careers-[^.]+\.icims\.com"]),
    ("ADP",             [r"jobs\.adp\.com"]),
    ("Jobvite",         [r"jobs\.jobvite\.com"]),
    ("Breezy",          [r"breezy\.hr"]),
    ("Ashby",           [r"jobs\.ashbyhq\.com"]),
    ("Rippling",        [r"ats\.rippling\.com"]),
    ("LinkedIn",        [r"linkedin\.com/jobs"]),
    ("Indeed",          [r"indeed\.com/job", r"indeed\.com/viewjob"]),
    ("Glassdoor",       [r"glassdoor\.com/job", r"glassdoor\.com/Jobs"]),
    ("ZipRecruiter",    [r"ziprecruiter\.com/jobs"]),
    ("Wellfound",       [r"wellfound\.com/jobs", r"angel\.co/jobs"]),
    ("We Work Remotely",[r"weworkremotely\.com"]),
    ("Remotive",        [r"remotive\.com/job"]),
    ("RemoteOK",        [r"remoteok\.com"]),
    ("Jobicy",          [r"jobicy\.com"]),
    ("Rozee.pk",        [r"rozee\.pk"]),
    ("Mustakbil",       [r"mustakbil\.com"]),
    ("Bayt",            [r"bayt\.com"]),
    ("The Muse",        [r"themuse\.com/jobs"]),
    ("Arbeitnow",       [r"arbeitnow\.com"]),
]

APPLY_METHOD_MAP = {
    "LinkedIn": "portal",
    "Indeed": "portal",
    "Glassdoor": "portal",
    "ZipRecruiter": "portal",
    "Workday": "portal",
    "Greenhouse": "portal",
    "Lever": "portal",
    "Taleo": "portal",
    "BambooHR": "portal",
    "SmartRecruiters": "portal",
    "iCIMS": "portal",
    "Jobvite": "portal",
    "Rozee.pk": "portal",
    "Mustakbil": "portal",
    "Bayt": "portal",
    # Direct apply via email
    "We Work Remotely": "email",
    "Wellfound": "both",
    "Remotive": "portal",
    "RemoteOK": "portal",
}


def detect_portal(url: str) -> dict:
    """Detect job portal/ATS type from a URL."""
    if not url:
        return {"portal_name": "Unknown", "apply_method": "portal", "detected": False}

    url_lower = url.lower()
    for portal_name, patterns in PORTAL_PATTERNS:
        for pat in patterns:
            if re.search(pat, url_lower):
                return {
                    "portal_name": portal_name,
                    "apply_method": APPLY_METHOD_MAP.get(portal_name, "portal"),
                    "detected": True,
                }
    return {"portal_name": "Company Portal", "apply_method": "portal", "detected": False}


async def portal_detector_impl(jobs_json: str) -> str:
    """Detect portal types for a list of jobs and return enriched job list."""
    import json
    jobs = json.loads(jobs_json) if isinstance(jobs_json, str) else jobs_json
    if isinstance(jobs, dict):
        jobs = jobs.get("jobs", [])

    for job in jobs:
        url = job.get("url") or job.get("job_url", "")
        info = detect_portal(url)
        job["portal_type"] = info["portal_name"]
        job["apply_method"] = info["apply_method"]

    return json.dumps({"success": True, "jobs": jobs})


@function_tool
async def portal_detector_tool(jobs_json: str) -> str:
    """Detect the ATS/portal type for each matched job URL.
    Returns jobs enriched with portal_type and apply_method fields."""
    return await portal_detector_impl(jobs_json)
