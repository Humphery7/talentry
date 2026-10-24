import json
import logging
import re
from typing import Any

from google import genai

from config.settings import settings

logger = logging.getLogger(__name__)

FINAL_LIMIT = 10
MAX_DESCRIPTION = 400

SYSTEM_INSTRUCTION = """You are a technical recruiter ranking job openings for one candidate.

Use only the candidate profile and the candidate jobs provided. Judge fit on role,
skills, technologies, seniority, location, and workplace type. Do not invent facts
that are not in the profile or the job. If a field is unknown, treat it as unknown
rather than a reason to reject. Pick at most 10 jobs. If fewer than 10 are plausible,
return fewer. Sort the results best fit first and give each a score from 0 to 100,
where 90+ is an exceptional match. The reason must be one short sentence grounded
in the candidate and the job."""

RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "integer"},
                    "score": {"type": "number"},
                    "reason": {"type": "string"},
                },
                "required": ["job_id", "score", "reason"],
            },
        }
    },
    "required": ["recommendations"],
}


def _strip_html(html: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text, flags=re.I)
    text = re.sub(r"&amp;", "&", text, flags=re.I)
    text = re.sub(r"&lt;", "<", text, flags=re.I)
    text = re.sub(r"&gt;", ">", text, flags=re.I)
    text = re.sub(r"&quot;", '"', text, flags=re.I)
    text = re.sub(r"&#39;|&apos;", "'", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def _format_candidate(candidate: dict[str, Any], index: int) -> str:
    locations = ", ".join(candidate["locations"]) or "Unspecified"
    technologies = ", ".join(candidate["technologies"]) or "Unspecified"
    lines = [
        f"[{index}] Job ID: {candidate['id']}",
        f"Title: {candidate['title']}",
        f"Company: {candidate['company'] or 'Unspecified'}",
        f"Location: {locations}",
        f"Seniority: {candidate['seniority'] or 'Unspecified'}",
        f"Occupation: {candidate['occupation'] or 'Unspecified'}",
        f"Employment type: {candidate['employment_type'] or 'Unspecified'}",
        f"Workplace: {candidate['workplace_type'] or 'Unspecified'}",
        f"Technologies: {technologies}",
        f"Semantic similarity: {candidate['similarity']:.3f}",
    ]
    description = _strip_html(candidate["description"] or "")
    if description:
        lines.append(f"Description: {description[:MAX_DESCRIPTION]}")
    return "\n".join(lines)


def build_prompt(profile_text: str, candidates: list[dict[str, Any]]) -> str:
    jobs = "\n\n".join(
        _format_candidate(candidate, index)
        for index, candidate in enumerate(candidates, start=1)
    )
    return (
        f"CANDIDATE PROFILE\n{profile_text}\n\n"
        f"CANDIDATE JOBS ({len(candidates)} jobs, pre-ranked by semantic similarity)\n\n"
        f"{jobs}\n\n"
        f"Return the best up to {FINAL_LIMIT} job IDs for this candidate."
    )


_client_instance: genai.Client | None = None


def _client() -> genai.Client:
    global _client_instance
    if _client_instance is None:
        if not settings.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not set in talentry-career/.env")
        _client_instance = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client_instance


def _normalize(
    payload: Any, candidates: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    items = payload.get("recommendations") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return []

    by_id = {candidate["id"]: candidate for candidate in candidates}
    seen: set[int] = set()
    ranked: list[dict[str, Any]] = []

    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            job_id = int(item["job_id"])
            score = float(item["score"])
        except (KeyError, TypeError, ValueError):
            continue
        if job_id not in by_id or job_id in seen:
            continue

        reason = str(item.get("reason") or "").strip()[:300]
        seen.add(job_id)
        ranked.append(
            {
                "job": by_id[job_id],
                "score": max(0.0, min(100.0, score)),
                "reason": reason,
            }
        )
        if len(ranked) >= FINAL_LIMIT:
            break

    return ranked


def rank_candidates(
    profile_text: str, candidates: list[dict[str, Any]]
) -> list[dict[str, Any]] | None:
    if not candidates:
        return []

    try:
        interaction = _client().interactions.create(
            model=settings.GEMINI_MODEL,
            input=build_prompt(profile_text, candidates),
            system_instruction=SYSTEM_INSTRUCTION,
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": RESPONSE_SCHEMA,
            },
            response_mime_type="application/json",
            store=False,
        )
        payload = json.loads(interaction.output_text or "")
    except Exception:
        logger.exception("Could not rank jobs with the LLM")
        return None

    return _normalize(payload, candidates)
