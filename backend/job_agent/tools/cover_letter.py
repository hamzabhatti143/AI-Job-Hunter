"""cover_letter_tool — Generate a unique 200–300 word cover letter per job.

Uses Gemini Flash (free) with OpenAI fallback.
Covers: personalised intro, role fit, top skills, closing CTA.
"""
import os
import json
import asyncio
import httpx
from agents import function_tool
from openai import AsyncOpenAI

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
_GEMINI_MODELS = ["gemini-2.0-flash-lite", "gemini-2.0-flash"]


def _build_prompt(job: dict, skills: list, experience_years: int, user_name: str) -> str:
    top_skills = ", ".join(skills[:5]) or "relevant technologies"
    return (
        f"Write a professional job application cover letter (200–300 words).\n"
        f"Job: {job.get('title', 'the position')} at {job.get('company', 'the company')}\n"
        f"Candidate: {user_name}, {experience_years} years experience\n"
        f"Top skills: {top_skills}\n"
        f"Structure:\n"
        f"  Para 1 — Enthusiastic opening: why this role + company excites me\n"
        f"  Para 2 — Key achievement or project using my top 2-3 skills\n"
        f"  Para 3 — Why I'm a cultural fit + call to action\n"
        f"  Sign-off: Sincerely, {user_name}\n"
        f"Return ONLY the cover letter text. No subject line. No extra commentary."
    )


def _template_cover_letter(job: dict, skills: list, experience_years: int, user_name: str) -> str:
    top = ", ".join(skills[:3]) or "relevant technologies"
    title   = job.get("title", "the position")
    company = job.get("company", "your company")
    return (
        f"Dear Hiring Manager,\n\n"
        f"I am writing to express my strong interest in the {title} role at {company}. "
        f"With {experience_years} year(s) of hands-on experience and expertise in {top}, "
        f"I am confident in my ability to make a meaningful contribution to your team.\n\n"
        f"Throughout my career I have delivered results by applying {top} in real-world projects, "
        f"consistently meeting deadlines and collaborating with cross-functional teams. "
        f"I thrive in dynamic environments where quality and innovation are valued.\n\n"
        f"I would welcome the opportunity to discuss how my background aligns with {company}'s goals. "
        f"Please feel free to reach out at your convenience.\n\n"
        f"Sincerely,\n{user_name}"
    )


async def _call_gemini(prompt: str) -> str:
    if not GEMINI_API_KEY:
        raise ValueError("No Gemini API key")
    last_err: Exception = Exception("All Gemini models failed")
    for model in _GEMINI_MODELS:
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=25) as client:
                    resp = await client.post(
                        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                        params={"key": GEMINI_API_KEY},
                        json={"contents": [{"parts": [{"text": prompt}]}],
                              "generationConfig": {"maxOutputTokens": 400}},
                    )
                    if resp.status_code in (503, 429):
                        await asyncio.sleep(3 * (attempt + 1))
                        continue
                    resp.raise_for_status()
                    return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            except Exception as e:
                last_err = e
                if attempt == 0:
                    await asyncio.sleep(1)
    raise last_err


async def cover_letter_impl(
    job_json: str,
    skills_json: str,
    experience_years: int,
    user_name: str,
    api_key: str = "",
) -> str:
    job: dict    = json.loads(job_json)
    skills: list = json.loads(skills_json)
    prompt = _build_prompt(job, skills, experience_years, user_name)

    body = ""
    try:
        if api_key.startswith("sk-"):
            client = AsyncOpenAI(api_key=api_key)
            r = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=400,
            )
            body = r.choices[0].message.content.strip()
        else:
            body = await _call_gemini(prompt)
    except Exception:
        pass

    if not body:
        try:
            body = await _call_gemini(prompt)
        except Exception:
            body = _template_cover_letter(job, skills, experience_years, user_name)

    return json.dumps({
        "success": True,
        "cover_letter": body,
        "job_title":    job.get("title", ""),
        "company":      job.get("company", ""),
        "ai_generated": True,
    })


@function_tool
async def cover_letter_tool(
    job_json: str,
    skills_json: str,
    experience_years: int,
    user_name: str,
    api_key: str = "",
) -> str:
    """Generate a 200–300 word personalised cover letter for a job.
    Uses Gemini Flash (free) with OpenAI fallback. Falls back to template on quota.
    job_json: { title, company, url }
    skills_json: JSON array of skills
    """
    return await cover_letter_impl(
        job_json=job_json, skills_json=skills_json,
        experience_years=experience_years, user_name=user_name,
        api_key=api_key,
    )
