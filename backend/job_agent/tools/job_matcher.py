"""STEP 4 — Score and rank jobs.
Scoring weights: Skills 40 | Experience 20 | Location 20 | Role Title 10 | Salary 10
Threshold: 50% minimum AND 2+ skill matches (when resume has skills).
Flag 70%+ as "Top Match", 50-69% as "Good Match".
Sort: matched_skills count desc → match_score desc.
"""
import json
import re
import uuid as uuid_module
from agents import function_tool
from db.database import AsyncSessionLocal
from db.models import JobMatch

STOP_WORDS = {'a','an','the','and','or','for','in','at','to','of','with','is','are','be','as','on','it','i'}

ROLE_DIRECT_ALIASES: dict[str, list[str]] = {
    "developer": ["engineer", "programmer", "dev"],
    "engineer":  ["developer", "programmer", "dev"],
    "frontend":  ["front-end", "front end", "ui", "web", "client-side"],
    "backend":   ["back-end", "back end", "server-side", "server"],
    "fullstack": ["full-stack", "full stack"],
    "designer":  ["ui/ux", "ux designer", "ui designer", "product designer"],
    "seo":       ["search engine optimization", "sem"],
    "devops":    ["sre", "platform engineer", "infrastructure engineer", "cloud engineer"],
    "mobile":    ["ios developer", "android developer", "app developer"],
    "data":      ["analytics", "analyst"],
    "scientist": ["researcher"],
}

ROLE_CONFLICTS: dict[str, list[str]] = {
    "frontend":  ["backend", "back-end", "devops", "infrastructure", "data science",
                  "machine learning", "security engineer", "qa engineer", "test engineer",
                  "data analyst", "data engineer", "mlops", "platform engineer"],
    "backend":   ["frontend", "front-end", "ui/ux", "product designer"],
    "fullstack": ["devops", "data scientist", "machine learning", "security"],
    "designer":  ["backend", "devops", "data", "security", "qa"],
    "devops":    ["frontend", "data scientist", "machine learning"],
    "seo":       ["backend engineer", "frontend engineer", "devops", "data scientist",
                  "machine learning", "security"],
    "data":      ["frontend developer", "devops", "designer"],
}

_SENIOR_WORDS = {"senior", "lead", "principal", "staff", "head", "director", "vp", "architect"}
_MID_WORDS    = {"mid", "intermediate", "associate"}
_JUNIOR_WORDS = {"junior", "entry", "intern", "trainee", "fresher", "graduate", "jr"}


def _word_in_text(word: str, text: str) -> bool:
    if word in text:
        return True
    for alias in ROLE_DIRECT_ALIASES.get(word, []):
        if alias in text:
            return True
    return False


def _is_conflicting(role_words: list[str], title: str) -> bool:
    for rw in role_words:
        for conflict in ROLE_CONFLICTS.get(rw, []):
            if conflict in title:
                return True
    return False


def _parse_salary_range(text: str) -> tuple[int | None, int | None]:
    """Extract min/max annual salary from text (USD/PKR/GBP etc.)."""
    patterns = [
        r'\$\s*(\d{1,3}(?:,\d{3})*|\d+)k?\s*[-–to]+\s*\$?\s*(\d{1,3}(?:,\d{3})*|\d+)k?',
        r'(\d{2,3}),?000\s*[-–to]+\s*(\d{2,3}),?000',
        r'(\d+)\s*lpa?\s*[-–to]+\s*(\d+)\s*lpa?',  # Indian LPA format
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            def _to_num(s: str) -> int:
                s = s.replace(",", "")
                n = float(s)
                if n < 1000:  # likely 'k' shorthand
                    n *= 1000
                return int(n)
            try:
                return _to_num(m.group(1)), _to_num(m.group(2))
            except Exception:
                pass
    return None, None


def _experience_salary_fit(salary_min: int | None, experience_years: int) -> int:
    """Return salary fit score (0-10). Neutral (5) when no salary data."""
    if salary_min is None:
        return 5  # neutral — most APIs don't expose salary

    # Very rough USD annual salary brackets by experience
    BRACKETS = [
        (0, 2,  20_000,  60_000),
        (2, 5,  50_000, 100_000),
        (5, 10, 80_000, 150_000),
        (10, 99, 120_000, 999_999),
    ]
    for (min_exp, max_exp, sal_low, sal_high) in BRACKETS:
        if min_exp <= experience_years < max_exp:
            if sal_low <= salary_min <= sal_high:
                return 10
            elif salary_min < sal_low * 0.5:
                return 2   # too low for experience
            else:
                return 6   # ok
    return 5


async def job_matcher_impl(
    jobs_json: str,
    skills_json: str,
    experience_years: int,
    location: str,
    user_id: str = "",
    role_preference: str = "",
) -> str:
    raw  = json.loads(jobs_json)
    jobs = raw.get("jobs", []) if isinstance(raw, dict) else raw

    raw_skills = json.loads(skills_json)
    skills     = raw_skills.get("skills", []) if isinstance(raw_skills, dict) else raw_skills
    skills_lower = {s.lower() for s in skills}

    core_role_words = [
        w for w in role_preference.lower().split()
        if w not in STOP_WORDS and len(w) > 2
    ] if role_preference else []

    user_loc = location.lower().strip()
    user_wants_remote = user_loc in ("remote", "anywhere", "worldwide", "wfh", "work from home", "")

    scored = []

    for job in jobs:
        if not isinstance(job, dict):
            continue

        title       = job.get("title", "").lower()
        tags_list   = [t.lower() for t in (job.get("tags") or [])]
        tags_text   = " ".join(tags_list)
        description = (job.get("description") or "").lower()
        title_tags  = f"{title} {tags_text}"
        full_text   = f"{title_tags} {description}"

        # Hard exclude conflicting roles
        if core_role_words and _is_conflicting(core_role_words, title):
            continue

        score = 0.0

        # ── 1. Role title relevance (10 pts) ──────────────────────────
        if core_role_words:
            hits  = sum(1 for w in core_role_words if _word_in_text(w, title_tags))
            ratio = hits / len(core_role_words)
            if ratio == 1.0:
                score += 10
            elif ratio >= 0.5:
                score += 7
            elif ratio > 0:
                score += 4
            else:
                continue  # zero role words in title — skip
        else:
            score += 5  # no preference → neutral

        # ── 2. Skills match (40 pts) ───────────────────────────────────
        if skills_lower:
            matched_skills = [s for s in skills_lower if s in full_text]
            base = (len(matched_skills) / len(skills_lower)) * 35
            title_hits = sum(1 for s in skills_lower if s in title_tags)
            bonus = min(title_hits * 1.5, 5)
            score += min(base + bonus, 40)
        else:
            score += 20  # no skills to compare → neutral

        # ── 3. Experience level match (20 pts) ────────────────────────
        has_senior = any(w in title for w in _SENIOR_WORDS)
        has_mid    = any(w in title for w in _MID_WORDS)
        has_junior = any(w in title for w in _JUNIOR_WORDS)

        if experience_years >= 7:
            if has_senior:          score += 20
            elif not has_junior:    score += 13
            else:                   score += 3
        elif experience_years >= 3:
            if has_mid or has_senior: score += 20
            elif not has_junior:      score += 16
            else:                     score += 8
        elif experience_years >= 1:
            if has_junior or has_mid: score += 20
            elif not has_senior:      score += 15
            else:                     score += 5
        else:
            if has_junior:          score += 20
            elif not has_senior:    score += 12
            else:                   score += 4

        # ── 4. Location match (20 pts) ────────────────────────────────
        job_loc = job.get("location", "").lower()
        job_is_remote = any(w in job_loc for w in ["remote", "worldwide", "anywhere", "global", "wfh"])

        if user_wants_remote:
            score += 20 if job_is_remote else 8
        elif job_is_remote:
            score += 0  # user wants specific location — remote gets no location points
        else:
            # Try city match, then country match
            matched_loc = False
            for term in user_loc.replace(",", " ").split():
                if len(term) > 2 and term in job_loc:
                    score += 20
                    matched_loc = True
                    break
            if not matched_loc:
                score += 0  # strict: no location match = 0 (not penalized but no bonus)

        # ── 5. Salary fit (10 pts) ────────────────────────────────────
        sal_min, _ = _parse_salary_range(full_text)
        score += _experience_salary_fit(sal_min, experience_years)

        matched_skills_list = [s for s in skills_lower if s in full_text] if skills_lower else []
        missing_skills_list = [s for s in skills_lower if s not in full_text] if skills_lower else []

        # Adaptive per-job skill threshold — description-length aware.
        # Many Pakistan/onsite boards return jobs with empty descriptions.
        # Penalising those for 0 skill matches would discard every real job.
        desc_len = len((job.get("description") or ""))
        if not skills_lower or desc_len < 100:
            per_job_threshold = 0   # can't judge skills — no description
        elif desc_len < 350:
            per_job_threshold = 1   # short description — require 1 match
        else:
            per_job_threshold = 2   # rich description — require 2 matches

        scored.append({
            **job,
            "match_score":       round(score, 2),
            "matched_skills":    matched_skills_list,
            "missing_skills":    missing_skills_list,
            "skill_match_count": len(matched_skills_list),
            "_skill_threshold":  per_job_threshold,
        })

    # ── Dual threshold:
    #    1) score ≥ 50 (overall quality)
    #    2) per-job skill match threshold (adaptive, see above)
    # ────────────────────────────────────────────────────────────────────
    def _qualifies(j: dict) -> bool:
        if j["match_score"] < 50:
            return False
        threshold = j.get("_skill_threshold", 0)
        if threshold and j["skill_match_count"] < threshold:
            return False
        return True

    qualified = sorted(
        [j for j in scored if _qualifies(j)],
        key=lambda x: (-x["skill_match_count"], -x["match_score"]),
    )[:25]

    for job in qualified:
        job["match_tier"] = "Top Match" if job["match_score"] >= 70 else "Good Match"

    # Save to DB
    matched_with_ids = []
    if user_id and qualified:
        try:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    for job in qualified:
                        job_id = uuid_module.uuid4()
                        session.add(JobMatch(
                            id=job_id,
                            user_id=uuid_module.UUID(user_id),
                            job_title=(job.get("title") or "")[:500],
                            company=(job.get("company") or "")[:500],
                            match_score=job["match_score"],
                            match_tier=job.get("match_tier"),
                            job_url=job.get("url", ""),
                            location=job.get("location", ""),
                            source=job.get("source", ""),
                            status="matched",
                            matched_skills=job.get("matched_skills") or [],
                            missing_skills=job.get("missing_skills") or [],
                        ))
                        matched_with_ids.append({**job, "db_job_id": str(job_id)})
        except Exception:
            matched_with_ids = qualified
    else:
        matched_with_ids = qualified

    return json.dumps({
        "success": True,
        "matched_jobs": matched_with_ids,
        "total_matched": len(matched_with_ids),
    })


@function_tool
async def job_matcher_tool(
    jobs_json: str, skills_json: str, experience_years: int,
    location: str, user_id: str = "", role_preference: str = "",
) -> str:
    """Score and rank jobs. Weights: Skills 40 | Experience 20 | Location 20 | Role 10 | Salary 10.
    Threshold: ≥50% score AND ≥2 skill matches (when resume has 3+ skills).
    70%+ flagged as 'Top Match'. 50-69% flagged as 'Good Match'.
    Returns matched_skills and missing_skills per job. Sorted by skill match count then score."""
    return await job_matcher_impl(
        jobs_json=jobs_json, skills_json=skills_json,
        experience_years=experience_years, location=location,
        user_id=user_id, role_preference=role_preference,
    )
