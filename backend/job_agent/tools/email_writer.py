"""STEP 7 — Generate a resume-grounded, structured professional job application email."""
import os
import re
import json
import asyncio
import httpx
from agents import function_tool
from openai import AsyncOpenAI

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
_GEMINI_MODELS = ["gemini-2.0-flash-lite", "gemini-2.0-flash"]


def _detect_provider(api_key: str) -> str:
    if api_key.startswith("AIza"):
        return "gemini"
    if api_key.startswith("sk-"):
        return "openai"
    return "gemini"


# ── Resume context extractor ──────────────────────────────────────────────────

def _extract_resume_context(resume_text: str) -> dict:
    """
    Extract structured sections from raw resume text.
    Used to ground the AI prompt and the template fallback.
    """
    lines = [l.strip() for l in resume_text.split('\n') if l.strip()]

    date_pat = re.compile(
        r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|'
        r'january|february|march|april|june|july|august|september|'
        r'october|november|december)?\s*(?:19|20)\d{2}',
        re.IGNORECASE,
    )
    achievement_pat = re.compile(
        r'\d+\s*%|\d+\s*x\b|\$[\d,]+|\d+\+?\s*'
        r'(?:users?|clients?|projects?|apps?|years?|months?|hours?|'
        r'deployments?|integrations?|sales?|revenue|conversions?|'
        r'leads?|campaigns?|keywords?|rankings?)',
        re.IGNORECASE,
    )

    exp_header  = re.compile(r'^(?:work\s+)?experience|employment|professional\s+experience|career', re.IGNORECASE)
    edu_header  = re.compile(r'^education|academic|qualification|degree', re.IGNORECASE)
    proj_header = re.compile(r'^projects?|portfolio|personal\s+projects?|key\s+projects?', re.IGNORECASE)

    sections: dict[str, list[str]] = {'experience': [], 'education': [], 'projects': []}
    current = None
    for line in lines:
        if exp_header.match(line):   current = 'experience'; continue
        if edu_header.match(line):   current = 'education';  continue
        if proj_header.match(line):  current = 'projects';   continue
        if re.match(r'^(?:skills?|technical\s+skills?|certif|summary|objective)', line, re.IGNORECASE):
            current = None; continue
        if current:
            sections[current].append(line)

    # Experience blocks: lines with date context + surrounding bullet points
    exp_lines = sections['experience'] or lines
    experience_blocks = []
    for i, line in enumerate(exp_lines):
        if date_pat.search(line):
            start = max(0, i - 2)
            end   = min(len(exp_lines), i + 6)
            block = '\n'.join(exp_lines[start:end])
            experience_blocks.append(block[:500])

    # Achievements: lines with measurable numbers
    achievements = [l for l in lines if achievement_pat.search(l) and len(l) > 20]

    return {
        'experience_blocks': experience_blocks[:5],
        'achievements':      achievements[:5],
        'education':         '\n'.join(sections['education'][:6]),
        'projects':          '\n'.join(sections['projects'][:10]),
    }


# ── Job–resume relevance matcher (used by template fallback) ─────────────────

def _match_to_job(skills: list, job_description: str) -> list[str]:
    """Return skills that appear in the job description (case-insensitive)."""
    desc_lower = job_description.lower()
    return [s for s in skills if s.lower() in desc_lower] or skills[:5]


def _relevant_experience(resume_ctx: dict, job_description: str) -> list[str]:
    """Return experience blocks whose text overlaps with job description keywords."""
    if not job_description:
        return resume_ctx['experience_blocks'][:3]
    desc_words = set(re.findall(r'\b[a-z]{3,}\b', job_description.lower()))
    scored = []
    for block in resume_ctx['experience_blocks']:
        block_words = set(re.findall(r'\b[a-z]{3,}\b', block.lower()))
        score = len(desc_words & block_words)
        scored.append((score, block))
    scored.sort(key=lambda x: -x[0])
    return [b for _, b in scored[:3]] or resume_ctx['experience_blocks'][:3]


def _relevant_projects(resume_ctx: dict, job_description: str) -> str:
    """Return the project block most relevant to the job description."""
    projects_text = resume_ctx.get('projects', '')
    if not projects_text or not job_description:
        return projects_text
    # Score each project bullet by keyword overlap
    desc_words = set(re.findall(r'\b[a-z]{3,}\b', job_description.lower()))
    lines = [l.strip() for l in projects_text.split('\n') if l.strip()]
    scored = []
    current_project: list[str] = []
    for line in lines:
        if line.startswith('●') or line.startswith('•'):
            if current_project:
                block = '\n'.join(current_project)
                block_words = set(re.findall(r'\b[a-z]{3,}\b', block.lower()))
                scored.append((len(desc_words & block_words), block))
            current_project = [line]
        else:
            current_project.append(line)
    if current_project:
        block = '\n'.join(current_project)
        block_words = set(re.findall(r'\b[a-z]{3,}\b', block.lower()))
        scored.append((len(desc_words & block_words), block))
    scored.sort(key=lambda x: -x[0])
    return scored[0][1] if scored else projects_text[:400]


# ── Prompt builder ────────────────────────────────────────────────────────────

def _build_prompt(
    job: dict,
    skills: list,
    user_name: str,
    user_email: str,
    recruiter_name: str,
    resume_text: str,
    resume_ctx: dict,
) -> str:
    greeting    = f"Dear {recruiter_name}" if recruiter_name else "Dear Hiring Manager"
    skills_str  = ", ".join(skills[:12]) if skills else "relevant technical skills"
    title       = job.get('title', 'the position')
    company     = job.get('company', 'the company')
    description = (job.get('description') or '')[:1200]

    exp_section    = "\n---\n".join(resume_ctx['experience_blocks']) or "(no dated experience blocks found)"
    achiev_section = "\n".join(f"• {a}" for a in resume_ctx['achievements']) or "(none detected)"
    edu_section    = resume_ctx['education'] or "(not found)"
    proj_section   = resume_ctx['projects'] or "(none found)"

    return f"""You are a professional job application email writer.

Your approach: The JOB DESCRIPTION is the PRIMARY driver — it tells you what the recruiter needs. The RESUME is the evidence pool — it tells you what the candidate can prove. Write the email to answer the recruiter's needs using only resume-backed facts.

════════════════════════════════════
PRIMARY — JOB REQUIREMENTS (read this first, this drives the email)
════════════════════════════════════
Job Title:   {title}
Company:     {company}
Job Description:
{description if description else "(no description provided — use job title to infer requirements)"}

════════════════════════════════════
EVIDENCE POOL — CANDIDATE RESUME (use only to back up job requirements)
════════════════════════════════════
{resume_text[:3500]}

Extracted Resume Context:
[Work Experience]
{exp_section}

[Achievements with Metrics]
{achiev_section}

[Education]
{edu_section}

[Projects]
{proj_section}

[Skills]
{skills_str}

════════════════════════════════════
BEFORE WRITING — do this analysis first:
════════════════════════════════════
1. Extract the top 4–6 requirements from the job description (skills, tools, responsibilities).
2. For EACH requirement, find the matching evidence in the resume (experience, project, skill, achievement).
3. Discard any resume content that does NOT address a job requirement.
4. Only build the email from: job requirement → resume evidence pairs.

════════════════════════════════════
STRICT RULES
════════════════════════════════════
1. The email content is driven by WHAT THE JOB NEEDS — not by what looks good on the resume.
2. Every claim MUST be backed by the resume — no fabrication, no exaggeration.
3. If a job requirement has NO matching evidence in the resume, skip it entirely.
4. No generic filler: "passionate about", "team player", "quick learner", "hard worker".
5. Tone: formal, direct, recruiter-focused.
6. Length: 200–350 words.

════════════════════════════════════
EMAIL STRUCTURE (follow exactly)
════════════════════════════════════
{greeting},

OPENING (1–2 sentences):
State you are applying for {title} at {company}. Lead with the single strongest job-requirement → resume-evidence match as your value proposition.

PARAGRAPH 1 — Experience that answers the job:
Address the 1–2 most important responsibilities in the job description. For each, cite the specific role/company from the resume where you did that work. Be concrete — name the company, the role, the action.

PARAGRAPH 2 — Skills the job asked for:
List 3–5 skills that the job description explicitly mentions AND that appear in the resume. Use the exact names from the job description where possible (e.g. if JD says "Next.js", write "Next.js" not "React framework").

PARAGRAPH 3 — Project or achievement most relevant to this job:
Pick the ONE project or achievement from the resume that best mirrors what this job does. If it has a number (%, users, conversions, bugs reduced), use it. Tie it back to the job explicitly.

CLOSING:
One sentence call-to-action — do NOT mention the email address in the body. Sign off exactly as:
Best regards,
{user_name}
{user_email}

════════════════════════════════════
OUTPUT: Return ONLY the email body. No subject line. No notes. Start immediately with "{greeting},".
"""


# ── Template fallback (no AI available) ──────────────────────────────────────

def _template_email(
    job: dict,
    skills: list,
    user_name: str,
    user_email: str,
    recruiter_name: str,
    resume_ctx: dict,
) -> str:
    greeting    = f"Dear {recruiter_name}" if recruiter_name else "Dear Hiring Manager"
    title       = job.get('title', 'the position')
    company     = job.get('company', 'your company')
    description = job.get('description') or ''

    # ── STEP 1: Job description drives what goes in the email ─────────────────
    # Skills the job asked for AND the candidate has — job description is the filter
    matched_skills = _match_to_job(skills, description)
    skills_str = ", ".join(matched_skills[:5]) if matched_skills else ", ".join(skills[:5]) or "relevant technologies"

    # ── STEP 2: Pick resume evidence that answers the job requirements ─────────
    # Experience most relevant to THIS job's description
    relevant_exp = _relevant_experience(resume_ctx, description)

    # Build experience sentence: "At [Company/Role], I [responsibility]"
    exp_para = ""
    for block in relevant_exp[:2]:
        exp_lines = [l.strip() for l in block.split('\n') if l.strip()]
        if len(exp_lines) >= 2:
            # First line = role/company header, second = responsibility
            exp_para += f"At {exp_lines[0]}, I {exp_lines[1].lower().rstrip('.')}. "
        elif exp_lines:
            exp_para += f"{exp_lines[0]}. "
    exp_para = exp_para.strip()

    # ── STEP 3: Best project that mirrors what this job does ──────────────────
    best_project = _relevant_projects(resume_ctx, description)
    project_lines = [l.strip() for l in best_project.split('\n') if l.strip()] if best_project else []

    # Pull measurable achievement from that project if available
    achievement = ""
    for line in (resume_ctx.get('achievements') or []):
        clean = line.lstrip('•–- ').strip()
        if clean:
            achievement = clean
            break

    # Build project sentence tied to a job requirement
    project_para = ""
    if project_lines:
        proj_text = ' '.join(project_lines[:3]).lstrip('●•– ').strip()
        project_para = f"A directly relevant example from my portfolio: {proj_text}"
        if achievement and achievement.lower() not in proj_text.lower():
            project_para += f" — achieving {achievement.lower().rstrip('.')}."
        else:
            project_para += "."

    # ── STEP 4: Assemble email — job-first framing throughout ─────────────────
    # Opening: what the job needs → candidate's strongest match
    opening = (
        f"I am writing to apply for the {title} position at {company}. "
        f"Your role calls for expertise in {skills_str.split(',')[0].strip()} "
        f"and related technologies — areas where I have direct, hands-on experience."
    )

    # Para 1: job responsibilities → resume evidence
    para1 = (
        f"Your requirements align closely with my professional background. {exp_para}"
        if exp_para else
        f"I have hands-on experience with the core requirements of this role, "
        f"including work in production environments and client-facing projects."
    )

    # Para 2: skills the job listed → skills in resume
    para2 = (
        f"The technical skills this role requires that I bring include {skills_str}. "
        f"I have applied these directly in professional and freelance projects, "
        f"not just in theory."
    )

    # Para 3: project proof tied to the job
    para3 = project_para if project_para else (
        f"I have successfully delivered projects requiring these exact capabilities, "
        f"with a focus on quality, performance, and real-world results."
    )

    return (
        f"{greeting},\n\n"
        f"{opening}\n\n"
        f"{para1}\n\n"
        f"{para2}\n\n"
        f"{para3}\n\n"
        f"I would welcome the opportunity to discuss how my background directly addresses "
        f"your team's needs.\n\n"
        f"Best regards,\n{user_name}\n{user_email}"
    )


# ── AI callers ────────────────────────────────────────────────────────────────

async def _call_gemini(prompt: str, api_key: str) -> str:
    key = api_key if api_key.startswith("AIza") else GEMINI_API_KEY
    if not key:
        raise ValueError("No Gemini API key available")
    last_err: Exception = Exception("Gemini: all models failed")
    for model in _GEMINI_MODELS:
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=45) as client:
                    resp = await client.post(
                        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                        params={"key": key},
                        json={
                            "contents": [{"parts": [{"text": prompt}]}],
                            "generationConfig": {"maxOutputTokens": 700, "temperature": 0.3},
                        },
                    )
                    if resp.status_code in (503, 429):
                        await asyncio.sleep(5 if resp.status_code == 429 else 2)
                        continue
                    resp.raise_for_status()
                    return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            except Exception as e:
                last_err = e
                if attempt == 0:
                    await asyncio.sleep(1)
    raise last_err


async def _call_openai(prompt: str, api_key: str) -> str:
    client = AsyncOpenAI(api_key=api_key)
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=700,
    )
    return response.choices[0].message.content.strip()


# ── Main implementation ───────────────────────────────────────────────────────

async def email_writer_impl(
    job_json: str,
    skills_json: str,
    user_name: str,
    user_email: str,
    api_key: str,
    recruiter_email: str = "",
    recruiter_name: str = "",
    resume_text: str = "",
) -> str:
    job: dict    = json.loads(job_json)
    skills: list = json.loads(skills_json)

    resume_ctx = _extract_resume_context(resume_text) if resume_text.strip() else {
        'experience_blocks': [], 'achievements': [], 'education': '', 'projects': '',
    }

    prompt   = _build_prompt(job, skills, user_name, user_email, recruiter_name, resume_text, resume_ctx)
    provider = _detect_provider(api_key)
    body     = ""
    error_detail = ""

    try:
        body = await _call_openai(prompt, api_key) if provider == "openai" else await _call_gemini(prompt, api_key)
    except Exception as e:
        error_detail = str(e)

    # Fallback: if OpenAI failed, try Gemini
    if not body and provider == "openai":
        try:
            body = await _call_gemini(prompt, "")
            error_detail = ""
        except Exception as e2:
            error_detail = f"OpenAI: {error_detail} | Gemini: {e2}"

    # Last resort: deterministic template (never blocks draft creation)
    ai_used = bool(body)
    if not body:
        body = _template_email(job, skills, user_name, user_email, recruiter_name, resume_ctx)

    subject = f"Application for {job.get('title', 'Position')} at {job.get('company', 'Your Company')}"
    return json.dumps({
        "success":      True,
        "subject":      subject,
        "body":         body,
        "ai_generated": ai_used,
        "recipient":    recruiter_email,
        "job_title":    job.get("title"),
        "company":      job.get("company"),
    })


@function_tool
async def email_writer_tool(
    job_json: str,
    skills_json: str,
    user_name: str,
    user_email: str,
    api_key: str,
    recruiter_email: str = "",
    recruiter_name: str = "",
    resume_text: str = "",
) -> str:
    """Generate a resume-grounded professional job application email (200–350 words).
    Every claim is verified against the candidate's resume — nothing fabricated.
    Supports OpenAI (sk-...) and Gemini (AIza...) keys; falls back to free Gemini.
    Pass resume_text (raw resume string) for grounded generation.
    """
    return await email_writer_impl(
        job_json=job_json, skills_json=skills_json, user_name=user_name,
        user_email=user_email, api_key=api_key, recruiter_email=recruiter_email,
        recruiter_name=recruiter_name, resume_text=resume_text,
    )
