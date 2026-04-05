"""STEP 8 — Prepare resume file for attachment."""
import os
import json
import base64
from agents import function_tool


async def file_attachment_impl(resume_path: str, candidate_name: str = "") -> str:
    try:
        if not os.path.exists(resume_path):
            return json.dumps({"success": False, "error": f"File not found: {resume_path}"})
        with open(resume_path, "rb") as f:
            content = f.read()
        ext = os.path.splitext(resume_path)[1].lower() or ".pdf"
        # Use a professional filename based on candidate name if available
        if candidate_name and candidate_name.strip() and candidate_name.lower() != "candidate":
            safe_name = "".join(c if c.isalnum() or c in " -_" else "" for c in candidate_name).strip().replace(" ", "_")
            filename = f"Resume_{safe_name}{ext}"
        else:
            filename = f"Resume{ext}"
        encoded = base64.b64encode(content).decode("utf-8")
        mime = "application/pdf" if ext == ".pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        return json.dumps({
            "success": True,
            "filename": filename,
            "mime_type": mime,
            "content_base64": encoded,
            "size_bytes": len(content),
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@function_tool
async def file_attachment_tool(resume_path: str) -> str:
    """Read resume file and encode it as base64 for email attachment.
    Returns JSON with filename, mime_type, content_base64, size_bytes.
    """
    return await file_attachment_impl(resume_path=resume_path)
