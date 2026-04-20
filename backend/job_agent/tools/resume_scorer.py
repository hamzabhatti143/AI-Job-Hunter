"""resume_score_tool — ATS compatibility score + improvement tips.

Scores resume against a specific job description.
Returns 0-100 score, matched keywords, gaps, actionable tips.
Uses Gemini Flash (free tier, low token usage).
"""
import os
import json
import asyncio
import httpx
from agents import function_tool

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
_GEMINI_MODELS = ["gemini-2.0-flash-lite", "gemini-2.0-flash"]


def _build_prompt(resume_text: str, job_description: str, job_title: str, company: str) -> str:
    # Truncate inputs to keep token usage low
    resume_excerpt = resume_text[:1500]
    jd_excerpt     = job_description[:1000]
    return (
        f"You are an ATS (Applicant Tracking System) evaluator.\n"
        f"Score this resume against the job description. Return JSON only.\n\n"
        f"Job: {job_title} at {company}\n"
        f"Job Description:\n{jd_excerpt}\n\n"
        f"Resume:\n{resume_excerpt}\n\n"
        f"Return this exact JSON (no markdown):\n"
        f'{{"ats_score": <0-100 integer>, '
        f'"matched_keywords": ["kw1","kw2",...], '
        f'"missing_keywords": ["kw1","kw2",...], '
        f'"tips": ["tip1","tip2","tip3"]}}'
    )


async def _call_gemini(prompt: str) -> dict:
    if not GEMINI_API_KEY:
        raise ValueError("No Gemini API key")
    for model in _GEMINI_MODELS:
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    resp = await client.post(
                        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                        params={"key": GEMINI_API_KEY},
                        json={"contents": [{"parts": [{"text": prompt}]}],
                              "generationConfig": {"maxOutputTokens": 300}},
                    )
                    if resp.status_code in (503, 429):
                        await asyncio.sleep(3 * (attempt + 1))
                        continue
                    resp.raise_for_status()
                    raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                    # Strip markdown code fences if present
                    if raw.startswith("```"):
                        raw = raw.split("```")[1]
                        if raw.startswith("json"):
                            raw = raw[4:]
                    return json.loads(raw)
            except json.JSONDecodeError:
                continue
            except Exception as e:
                if attempt == 0:
                    await asyncio.sleep(1)
    raise RuntimeError("Resume scoring failed — all Gemini models exhausted")


async def resume_scorer_impl(
    resume_text: str,
    job_json: str,
) -> str:
    job = json.loads(job_json) if isinstance(job_json, str) else job_json
    job_title       = job.get("title", "Unknown Role")
    company         = job.get("company", "Unknown Company")
    job_description = job.get("description", "")

    if not job_description:
        # No description to score against — return neutral
        return json.dumps({
            "success": True,
            "ats_score": 50,
            "matched_keywords": [],
            "missing_keywords": [],
            "tips": ["Job description not available — score is neutral."],
            "job_title": job_title,
            "company": company,
        })

    try:
        prompt = _build_prompt(resume_text, job_description, job_title, company)
        result = await _call_gemini(prompt)
        return json.dumps({
            "success": True,
            "ats_score":        result.get("ats_score", 0),
            "matched_keywords": result.get("matched_keywords", []),
            "missing_keywords": result.get("missing_keywords", []),
            "tips":             result.get("tips", []),
            "job_title":        job_title,
            "company":          company,
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e),
            "job_title": job_title,
            "company": company,
        })


@function_tool
async def resume_score_tool(resume_text: str, job_json: str) -> str:
    """Score a resume against a job description for ATS compatibility.
    Returns ats_score (0-100), matched/missing keywords, and improvement tips.
    job_json: { title, company, description }
    """
    return await resume_scorer_impl(resume_text=resume_text, job_json=job_json)
