"""Generate a professional job application email using Gemini API."""
import os
import re
import json
import asyncio
import httpx
from agents import function_tool

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
_GEMINI_MODELS = ["gemini-2.0-flash", "gemini-2.0-flash-lite"]


# ── Known portal names (for display cleaning only) ───────────────────────────

_KNOWN_PORTALS = {
    "bebee", "indeed", "linkedin", "glassdoor", "remoteok", "remotive",
    "weworkremotely", "we work remotely", "arbeitnow", "findwork", "jobicy",
    "themuse", "the muse", "adzuna", "smartrecruiters", "brightspyre",
    "bayt", "rozee", "theirstack", "ziprecruiter", "monster", "careerbuilder",
    "dice", "simplyhired", "jooble", "google jobs", "serpapi", "interviewpal",
    "joinimagine", "trabajo", "acca global", "acca",
}

_SOURCE_IN_TITLE = re.compile(
    r'\b(?:theirstack|rozee|bebee|indeed|linkedin|glassdoor|arbeitnow|'
    r'findwork|adzuna|ziprecruiter|monster|jooble|remoteok|remotive|'
    r'serpapi|brightspyre|smartrecruiters|interviewpal|joinimagine)\b',
    re.IGNORECASE,
)
_LONG_NUMBER = re.compile(r'\b\d{5,}\b')

_LOCATION_SUFFIX = re.compile(
    r'\s*[·|\-–—/,]\s*(?:remote|hybrid|onsite|on.?site|'
    r'karachi|lahore|islamabad|rawalpindi|dubai|riyadh|london|berlin|'
    r'new\s+york|san\s+francisco|los\s+angeles|chicago|toronto|'
    r'bangalore|hyderabad|mumbai|singapore|sydney|[a-z]{3,}(?:,\s*[a-z]{2})?'
    r')[\s·|,\-]*$',
    re.IGNORECASE,
)
_PARENS_NOISE = re.compile(r'\s*\([^)]{1,30}\)\s*$')
_TRAIL_SEP    = re.compile(r'[\s·\-–—|/,]+$')

_COMPANY_SUFFIX = re.compile(
    r'\b(?:limited|ltd\.?|inc\.?|llc|pvt\.?|private|plc|corp\.?|'
    r'solutions|technologies|tech|services|group|holdings|enterprises|'
    r'consulting|associates|partners|labs|works|systems)\b',
    re.IGNORECASE,
)
_LOCATION_WORD = re.compile(
    r'\b(?:lahore|karachi|islamabad|rawalpindi|peshawar|quetta|multan|faisalabad|'
    r'dubai|riyadh|abu\s*dhabi|london|berlin|toronto|sydney|singapore|'
    r'new\s*york|san\s*francisco|pune|bangalore|hyderabad|mumbai|delhi|'
    r'punjab|sindh|kpk|balochistan|pakistan|remote|worldwide|global)\b',
    re.IGNORECASE,
)


def _looks_like_portal(name: str) -> bool:
    return (name or "").strip().lower() in _KNOWN_PORTALS


def _is_dirty(title: str) -> bool:
    return bool(_SOURCE_IN_TITLE.search(title) or _LONG_NUMBER.search(title))


def _regex_split_dirty(raw: str) -> tuple[str, str]:
    cuts = []
    for pat in [_COMPANY_SUFFIX, _SOURCE_IN_TITLE, _LOCATION_WORD, _LONG_NUMBER]:
        m = pat.search(raw)
        if m:
            cuts.append(m.start())
    if not cuts:
        return raw.strip(), ""
    cut       = min(cuts)
    title     = raw[:cut].strip(' ,·|–-\t')
    remainder = raw[cut:].strip()
    company   = ""
    rest_cuts = []
    for pat in [_SOURCE_IN_TITLE, _LOCATION_WORD, _LONG_NUMBER]:
        m = pat.search(remainder)
        if m:
            rest_cuts.append(m.start())
    if rest_cuts:
        co = remainder[:min(rest_cuts)].strip(' ,·|–-\t')
        if co:
            company = co
    elif remainder:
        m = _COMPANY_SUFFIX.search(remainder)
        company = remainder[:m.end()].strip() if m else remainder.strip()
    return (title or raw.strip()), company


def _clean_job_title(title: str) -> str:
    if not (title or "").strip():
        return "Open Position"
    t = _LOCATION_SUFFIX.sub('', title).strip()
    t = _PARENS_NOISE.sub('', t).strip()
    t = _TRAIL_SEP.sub('', t).strip()
    return re.sub(r"[A-Za-z]+('[A-Za-z]+)?", lambda m: m.group(0).capitalize(), t) if t else "Open Position"


def _extract_company_from_url(url: str) -> str:
    if not url:
        return ""
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc.lower()
        host = re.sub(r'^(?:www\.|careers\.|jobs\.|apply\.|work\.)', '', host)
        domain = host.split('.')[0]
        domain = re.sub(r'[\-_]', ' ', domain).strip()
        if len(domain) > 2 and not _looks_like_portal(domain):
            return domain.title()
    except Exception:
        pass
    return ""


def _resolve_company(company: str, job_url: str) -> str:
    clean = (company or "").strip()
    if clean and clean.lower() not in ("this company", "n/a", "null", "none", "") and not _looks_like_portal(clean):
        return clean
    from_url = _extract_company_from_url(job_url)
    if from_url:
        return from_url
    return "your organization"


# ── Sync cleaner used by dashboard listing (no LLM, fast) ────────────────────

def clean_job_fields_sync(title: str, company: str, url: str = "") -> tuple[str, str]:
    """Regex-only cleaning for job-card display. No API calls."""
    raw_t = (title   or "").strip()
    raw_c = (company or "").strip()
    if not _looks_like_portal(raw_c) and not _is_dirty(raw_t):
        return _clean_job_title(raw_t), _resolve_company(raw_c, url)
    reg_t, reg_c = _regex_split_dirty(raw_t)
    return _clean_job_title(reg_t), (reg_c or _resolve_company(raw_c, url))


# ── Resume field extractors ───────────────────────────────────────────────────

_PHONE_PAT = re.compile(
    r'(?:\+?\d{1,3}[\s\-.])?(?:\(?\d{2,4}\)?[\s\-.])?'
    r'\d{3,4}[\s\-.]\d{3,4}(?:[\s\-.]\d{2,4})?'
)
_EMAIL_PAT = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')


def _extract_phone(resume_text: str) -> str:
    m = _PHONE_PAT.search(resume_text)
    return m.group(0).strip() if m else ""


def _extract_email_from_resume(resume_text: str) -> str:
    m = _EMAIL_PAT.search(resume_text)
    return m.group(0).strip() if m else ""


def _extract_name_from_resume(resume_text: str) -> str:
    """Extract candidate name from the first lines of the resume."""
    lines = [l.strip() for l in resume_text.split('\n') if l.strip()]
    for line in lines[:6]:
        if '@' in line:
            continue
        if re.search(r'\d{3,}', line):
            continue
        if re.match(r'^(?:resume|cv|curriculum|objective|summary|profile|skills|experience|education)', line, re.IGNORECASE):
            continue
        if line.startswith('http'):
            continue
        words = line.split()
        if 2 <= len(words) <= 4 and all(re.match(r'^[A-Za-z][\w\.\-]*$', w) for w in words):
            return ' '.join(w.capitalize() for w in words)
    return ""


# ── Gemini caller ─────────────────────────────────────────────────────────────

async def _call_gemini(prompt: str) -> str:
    key = GEMINI_API_KEY
    if not key:
        raise ValueError("GEMINI_API_KEY not set")
    last_err: Exception = Exception("All Gemini models failed")
    for model in _GEMINI_MODELS:
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=45) as client:
                    resp = await client.post(
                        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                        params={"key": key},
                        json={
                            "contents": [{"parts": [{"text": prompt}]}],
                            "generationConfig": {"maxOutputTokens": 600, "temperature": 0.2},
                        },
                    )
                    if resp.status_code in (429, 503):
                        await asyncio.sleep(5 if resp.status_code == 429 else 2)
                        continue
                    resp.raise_for_status()
                    return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            except Exception as e:
                last_err = e
                if attempt == 0:
                    await asyncio.sleep(1)
    raise last_err


# ── Prompt ────────────────────────────────────────────────────────────────────

def _build_prompt(
    raw_job_title: str,
    raw_company: str,
    job_url: str,
    user_name: str,
    user_email: str,
    user_phone: str,
) -> str:
    phone_line = f"\n{user_phone}" if user_phone else ""
    return f"""You are writing a professional job application email.

The job listing data below may be messy — the job title field sometimes contains
the company name, city, source portal name, or ID numbers all concatenated together.
You must extract the real job title and real company name yourself before writing.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RAW JOB DATA (may be dirty — extract carefully)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Raw job title field : "{raw_job_title}"
Raw company field   : "{raw_company}"
Job URL             : "{job_url}"

Instructions for extraction:
- Job title  → extract ONLY the actual position name. Remove company names, cities,
               countries, source/portal names (Bebee, Rozee, Theirstack, Indeed etc.),
               numbers, and IDs.
               Example: "Frontend Developer Systems Limited Lahore Punjab Theirstack 663983145"
               → real title is "Frontend Developer"
- Company    → the real hiring company. If the company field is a job portal name
               (Bebee, Indeed, LinkedIn, Rozee, Glassdoor, Theirstack, Bayt, RemoteOK etc.)
               then ignore it and find the company embedded in the raw title field instead.
               Example: company field "Bebee", raw title contains "Systems Limited"
               → real company is "Systems Limited"
               If no company can be found anywhere → use "the hiring company"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
APPLICANT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Name  : {user_name}
Email : {user_email}  ← use this exact email in sign-off
{"Phone : " + user_phone if user_phone else "Phone : (none — omit from sign-off)"}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EMAIL FORMAT (follow exactly)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Subject: Application for [REAL JOB TITLE] – {user_name}

Dear Hiring Manager,

I hope this message finds you well.

I am writing to express my interest in the position of [REAL JOB TITLE] at
[REAL COMPANY]. I have attached my resume for your review, which outlines
my skills and experience relevant to this role.

I would appreciate the opportunity to discuss how my background and abilities
align with your team's needs.

Thank you for your time and consideration. I look forward to your response.

Kind regards,
{user_name}
{user_email}{phone_line}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Replace [REAL JOB TITLE] and [REAL COMPANY] with the values you extracted.
2. Never write portal names (Bebee, Rozee, Indeed etc.) as the company.
3. Never include city, country, source name, or ID numbers anywhere in the email.
4. Never leave a blank where a value should be (e.g. "at ." or "for .").
5. Use exactly {user_email} in the sign-off — never extract email from anywhere else.
6. Return ONLY the email starting with "Subject:". No explanation, no notes.
"""


# ── Fallback template (when Gemini unavailable) ───────────────────────────────

def _fallback_email(
    job_title: str,
    company: str,
    user_name: str,
    user_email: str,
    user_phone: str,
) -> tuple[str, str]:
    phone_line = f"\n{user_phone}" if user_phone else ""
    subject = f"Application for {job_title} \u2013 {user_name}"
    body = "\n".join([
        "Dear Hiring Manager,",
        "",
        "I hope this message finds you well.",
        "",
        f"I am writing to express my interest in the position of {job_title} at "
        f"{company}. I have attached my resume for your review, which outlines "
        f"my skills and experience relevant to this role.",
        "",
        "I would appreciate the opportunity to discuss how my background and abilities "
        "align with your team\u2019s needs.",
        "",
        "Thank you for your time and consideration. I look forward to your response.",
        "",
        "Kind regards,",
        user_name,
        f"{user_email}{phone_line}",
    ])
    return subject, body


# ── Subject / body splitter ───────────────────────────────────────────────────

def _split_subject_body(text: str, fallback_subject: str) -> tuple[str, str]:
    lines = text.strip().splitlines()
    if lines and lines[0].lower().startswith("subject:"):
        subject = lines[0][len("subject:"):].strip()
        body    = "\n".join(lines[1:]).lstrip("\n")
        return subject, body
    return fallback_subject, text.strip()


# ── Post-write scanner ────────────────────────────────────────────────────────

_SCAN_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r'Dear\s*,',         re.IGNORECASE), 'Dear ,'),
    (re.compile(r'\bat \.',          re.IGNORECASE), 'at .'),
    (re.compile(r'\bfor \.',         re.IGNORECASE), 'for .'),
    (re.compile(r'\bthis company\b', re.IGNORECASE), 'this company'),
    (re.compile(r'\bundefined\b',    re.IGNORECASE), 'undefined'),
    (re.compile(r'\bnull\b',         re.IGNORECASE), 'null'),
    (re.compile(r'\{\{'),                            '{{'),
    (re.compile(r'\}\}'),                            '}}'),
    (re.compile(r'  +'),                             'double space'),
]


def _scan_and_fix(subject: str, body: str, company: str, job_title: str) -> tuple[str, str, list[str]]:
    combined = subject + "\n" + body
    issues   = [label for pat, label in _SCAN_RULES if pat.search(combined)]
    if not issues:
        return subject, body, []
    fixes = [
        (re.compile(r'Dear\s*,',         re.IGNORECASE), "Dear Hiring Manager,"),
        (re.compile(r'\bat \.',          re.IGNORECASE), f"at {company}." if company else "in my previous role."),
        (re.compile(r'\bfor \.',         re.IGNORECASE), f"for {job_title}." if job_title else "for this position."),
        (re.compile(r'\bthis company\b', re.IGNORECASE), company or "your organization"),
        (re.compile(r'\bundefined\b',    re.IGNORECASE), ""),
        (re.compile(r'\bnull\b',         re.IGNORECASE), ""),
        (re.compile(r'\{\{[^}]*\}\}'),                   ""),
        (re.compile(r'  +'),                             " "),
    ]
    s, b = subject, body
    for pat, rep in fixes:
        s = pat.sub(rep, s).strip()
        b = pat.sub(rep, b)
    b = re.sub(r'\n{3,}', '\n\n', b).strip()
    return s, b, issues


# ── Validate ──────────────────────────────────────────────────────────────────

def _validate(user_name: str, user_email: str) -> str | None:
    if not (user_email or "").strip():
        return "User email missing."
    if not (user_name or "").strip():
        return "User name missing."
    return None


# ── Main implementation ───────────────────────────────────────────────────────

async def email_writer_impl(
    job_title: str,
    company_name: str,
    user_name: str,
    user_email: str,
    job_url: str = "",
    user_phone: str = "",
    hiring_manager_name: str = "",
) -> str:
    err = _validate(user_name, user_email)
    if err:
        return json.dumps({"status": "failed", "error": err, "subject": "", "body": "", "to_email": None})

    # Regex-cleaned versions used as fallback display values and for scanner
    reg_title, reg_company = clean_job_fields_sync(job_title, company_name, job_url)

    prompt           = _build_prompt(job_title, company_name, job_url, user_name, user_email, user_phone)
    fallback_subject = f"Application for {reg_title} \u2013 {user_name}"
    ai_raw           = ""
    ai_used          = False

    try:
        ai_raw  = await _call_gemini(prompt)
        ai_used = True
    except Exception:
        pass

    if ai_raw:
        subject, body = _split_subject_body(ai_raw, fallback_subject)
    else:
        subject, body = _fallback_email(reg_title, reg_company, user_name, user_email, user_phone)

    subject, body, issues = _scan_and_fix(subject, body, reg_company, reg_title)

    unfixable = [i for i in issues if i in ("{{", "}}", "undefined", "null")]
    if unfixable:
        return json.dumps({
            "status":  "failed",
            "error":   f"Some fields are missing for {reg_company}. Please complete manually before saving.",
            "subject": subject,
            "body":    body,
            "to_email": None,
        })

    return json.dumps({
        "status":      "ready",
        "subject":     subject,
        "body":        body,
        "to_email":    None,
        "error":       None,
        "job_title":   reg_title,
        "company":     reg_company,
        "ai_generated": ai_used,
        "scan_issues": issues,
    })


@function_tool
async def email_writer_tool(
    job_title: str,
    company_name: str,
    user_name: str,
    registered_email: str,
    job_url: str = "",
    user_phone: str = "",
    hiring_manager_name: str = "",
) -> str:
    """Write a professional job application email using Gemini.

    Passes raw scraped job data directly to Gemini with explicit instructions to
    extract the real job title and company name — handling dirty concatenated fields
    like 'Frontend Developer Systems Limited Lahore Theirstack 663983145' correctly.
    Falls back to a clean regex-based template if Gemini is unavailable.
    """
    return await email_writer_impl(
        job_title=job_title,
        company_name=company_name,
        user_name=user_name,
        user_email=registered_email,
        job_url=job_url,
        user_phone=user_phone,
        hiring_manager_name=hiring_manager_name,
    )
