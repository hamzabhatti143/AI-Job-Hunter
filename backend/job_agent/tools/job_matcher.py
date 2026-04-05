"""STEP 4 — Score and rank jobs. Strict 65% threshold + role conflict exclusion."""
import json
import uuid as uuid_module
from agents import function_tool
from db.database import AsyncSessionLocal
from db.models import JobMatch

STOP_WORDS = {'a','an','the','and','or','for','in','at','to','of','with','is','are','be','as','on','it','i'}

# Direct aliases — treated as exact equivalents for scoring
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

# Words that signal an OPPOSITE role — if these appear in a job title
# and the role_preference word is the key, exclude the job entirely
ROLE_CONFLICTS: dict[str, list[str]] = {
    "frontend":  ["backend", "back-end", "devops", "infrastructure", "data science",
                  "machine learning", "security engineer", "qa engineer", "test engineer",
                  "data analyst", "data engineer", "mlops", "platform engineer"],
    "backend":   ["frontend", "front-end", "ui/ux", "product designer"],
    "fullstack":  ["devops", "data scientist", "machine learning", "security"],
    "designer":  ["backend", "devops", "data", "security", "qa"],
    "devops":    ["frontend", "data scientist", "machine learning"],
    "seo":       ["backend engineer", "frontend engineer", "devops", "data scientist",
                  "machine learning", "security"],
    "data":      ["frontend developer", "devops", "designer"],
}


def _word_in_text(word: str, text: str) -> bool:
    """Check word or any of its direct aliases appear in text."""
    if word in text:
        return True
    for alias in ROLE_DIRECT_ALIASES.get(word, []):
        if alias in text:
            return True
    return False


def _is_conflicting(role_words: list[str], title: str) -> bool:
    """Return True if job title clearly conflicts with the role preference."""
    for rw in role_words:
        for conflict in ROLE_CONFLICTS.get(rw, []):
            if conflict in title:
                return True
    return False


async def job_matcher_impl(
    jobs_json: str,
    skills_json: str,
    experience_years: int,
    location: str,
    user_id: str = "",
    role_preference: str = "",
) -> str:
    raw = json.loads(jobs_json)
    jobs = raw.get("jobs", []) if isinstance(raw, dict) else raw

    raw_skills = json.loads(skills_json)
    skills = raw_skills.get("skills", []) if isinstance(raw_skills, dict) else raw_skills
    skills_lower = {s.lower() for s in skills}

    core_role_words = [
        w for w in role_preference.lower().split()
        if w not in STOP_WORDS and len(w) > 2
    ] if role_preference else []

    scored = []

    for job in jobs:
        if not isinstance(job, dict):
            continue

        title       = job.get("title", "").lower()
        tags_list   = [t.lower() for t in job.get("tags", [])]
        tags_text   = " ".join(tags_list)
        description = (job.get("description", "") or "").lower()
        title_tags  = f"{title} {tags_text}"          # primary signal
        full_text   = f"{title_tags} {description}"   # all text for skill scan

        # ── Hard exclude: role conflict ─────────────────────────────
        if core_role_words and _is_conflicting(core_role_words, title):
            continue

        score = 0.0

        # ── 1. Role relevance (50 pts) ─────────────────────────────
        if core_role_words:
            # Count how many core role words (or their direct aliases) appear in title+tags
            hits = sum(1 for w in core_role_words if _word_in_text(w, title_tags))
            ratio = hits / len(core_role_words)

            if ratio == 1.0:
                role_score = 50   # all words matched
            elif ratio >= 0.5:
                role_score = 32   # majority matched
            elif ratio > 0:
                role_score = 16   # minority matched (one word)
            else:
                # Zero role words/aliases in title+tags — skip
                continue

            score += role_score
        else:
            score += 25  # no preference → neutral

        # ── 2. Skill overlap (30 pts) ──────────────────────────────
        matched_skills = [s for s in skills_lower if s in full_text]
        if skills_lower:
            base_skill = (len(matched_skills) / len(skills_lower)) * 30
            # Extra: skills appearing in title/tags are stronger signals
            title_skill_hits = sum(1 for s in skills_lower if s in title_tags)
            bonus = min(title_skill_hits * 2, 8)
            score += min(base_skill + bonus, 30)

        # ── 3. Location (15 pts) ───────────────────────────────────
        job_loc = job.get("location", "").lower()
        user_loc = location.lower().strip()
        job_is_remote = any(w in job_loc for w in ["remote", "worldwide", "anywhere", "global"])
        if job_is_remote:
            score += 15  # remote jobs are accessible from anywhere
        elif user_loc and user_loc in job_loc:
            score += 15  # exact location match
        elif user_loc in ("remote", "anywhere", "worldwide"):
            score += 15  # user explicitly wants remote

        # ── 4. Seniority alignment (5 pts max) ────────────────────
        if experience_years >= 5 and any(w in title for w in ["senior","lead","principal","staff","head"]):
            score += 5
        elif 2 <= experience_years < 5 and any(w in title for w in ["mid","intermediate"]):
            score += 5
        elif experience_years < 2 and any(w in title for w in ["junior","entry","associate","intern","trainee"]):
            score += 5
        else:
            score += 1  # minimal bonus — don't let seniority mismatch kill score entirely

        scored.append({
            **job,
            "match_score": round(score, 2),
            "matched_skills": matched_skills,
        })

    # ── Strict 65% threshold — no fallback ────────────────────────
    matched = sorted(
        [j for j in scored if j["match_score"] >= 65],
        key=lambda x: -x["match_score"]
    )[:20]

    # Save to DB
    matched_with_ids = []
    if user_id and matched:
        try:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    for job in matched:
                        job_id = uuid_module.uuid4()
                        session.add(JobMatch(
                            id=job_id,
                            user_id=uuid_module.UUID(user_id),
                            job_title=(job.get("title") or "")[:500],
                            company=(job.get("company") or "")[:500],
                            match_score=job["match_score"],
                            job_url=job.get("url", ""),
                            location=job.get("location", ""),
                            status="matched",
                        ))
                        matched_with_ids.append({**job, "db_job_id": str(job_id)})
        except Exception:
            matched_with_ids = matched
    else:
        matched_with_ids = matched

    return json.dumps({
        "success": True,
        "matched_jobs": matched_with_ids,
        "total_matched": len(matched_with_ids),
    })


@function_tool
async def job_matcher_tool(
    jobs_json: str,
    skills_json: str,
    experience_years: int,
    location: str,
    user_id: str = "",
    role_preference: str = "",
) -> str:
    """Strict role-aware job scorer. 65% minimum threshold.
    Conflicting roles (e.g. backend jobs when frontend requested) are hard-excluded.
    Returns JSON with matched_jobs (each has db_job_id) and total_matched count.
    """
    return await job_matcher_impl(
        jobs_json=jobs_json, skills_json=skills_json,
        experience_years=experience_years, location=location,
        user_id=user_id, role_preference=role_preference,
    )
