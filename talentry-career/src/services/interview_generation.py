"""Generate one interview prep assessment with Gemini and save it."""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

import psycopg
from pydantic import ValidationError

from schemas.interview import Assessment, compute_progress, public_assessment
from services import interview_store
from services.gemini import generate_json

logger = logging.getLogger(__name__)

MAX_JOB_DESCRIPTION = 6_000
MAX_CV_TEXT = 8_000

SYSTEM_INSTRUCTION = """You design realistic, job-specific interview preparation assessments for one candidate.
Use only the job and candidate profile provided. Never invent candidate experience.
Choose the sections and number of questions that actually fit this job and seniority.
Return JSON that matches the requested schema."""

GENERATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "role_family": {"type": "string"},
        "summary": {"type": "string"},
        "estimated_minutes": {"type": "integer"},
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "type": {
                        "type": "string",
                        "enum": [
                            "general",
                            "behavioural",
                            "coding",
                            "technical",
                            "role_specific",
                            "system_design",
                            "other",
                        ],
                    },
                    "title": {"type": "string"},
                    "priority": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                    },
                    "description": {"type": "string"},
                    "estimated_minutes": {"type": "integer"},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "type": {
                                    "type": "string",
                                    "enum": [
                                        "text_response",
                                        "multiple_choice",
                                        "external_practice",
                                        "debugging",
                                        "code_reading",
                                        "sql_exercise",
                                        "scenario",
                                    ],
                                },
                                "question": {"type": "string"},
                                "instructions": {"type": "string"},
                                "topic": {"type": "string"},
                                "difficulty": {
                                    "type": "string",
                                    "enum": ["easy", "medium", "hard"],
                                },
                                "relevance": {
                                    "type": "string",
                                    "enum": ["high", "medium", "low"],
                                },
                                "estimated_minutes": {"type": "integer"},
                                "options": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "id": {"type": "string"},
                                            "text": {"type": "string"},
                                        },
                                        "required": ["id", "text"],
                                    },
                                },
                                "resource": {
                                    "type": "object",
                                    "properties": {
                                        "provider": {"type": "string"},
                                        "title": {"type": "string"},
                                        "url": {"type": "string"},
                                    },
                                    "required": ["provider", "title", "url"],
                                },
                                "evaluation": {
                                    "type": "object",
                                    "properties": {
                                        "method": {
                                            "type": "string",
                                            "enum": [
                                                "objective",
                                                "llm_rubric",
                                                "activity",
                                            ],
                                        },
                                        "correct_option_id": {"type": "string"},
                                        "explanation": {"type": "string"},
                                        "model_answer": {"type": "string"},
                                        "rubric": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "criterion": {"type": "string"},
                                                    "weight": {"type": "number"},
                                                    "description": {
                                                        "type": "string"
                                                    },
                                                },
                                                "required": [
                                                    "criterion",
                                                    "weight",
                                                    "description",
                                                ],
                                            },
                                        },
                                    },
                                    "required": ["method"],
                                },
                            },
                            "required": [
                                "id",
                                "type",
                                "question",
                                "topic",
                                "difficulty",
                                "relevance",
                                "estimated_minutes",
                                "evaluation",
                            ],
                        },
                    },
                },
                "required": [
                    "id",
                    "type",
                    "title",
                    "priority",
                    "description",
                    "estimated_minutes",
                    "items",
                ],
            },
        },
    },
    "required": [
        "title",
        "role_family",
        "summary",
        "estimated_minutes",
        "sections",
    ],
}


class GenerationError(RuntimeError):
    pass


class JobNotFound(RuntimeError):
    pass


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


def _json_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except ValueError:
            return []
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    return []


def _profile_text(profile: dict[str, Any] | None) -> str:
    if not profile:
        return "No candidate profile supplied; design for the job only."

    parts: list[str] = []

    def add(label: str, value: str | None) -> None:
        text = (value or "").strip()
        if text:
            parts.append(f"{label}: {text}")

    add("Headline", profile.get("headline"))
    add("Current title", profile.get("current_title"))
    years = profile.get("years_experience")
    if years is not None:
        parts.append(f"Years of experience: {years}")
    add("Location", profile.get("location"))
    add("Summary", profile.get("summary"))
    cv_text = (profile.get("cv_data") or "").strip()
    if cv_text:
        parts.append(f"CV:\n{cv_text[:MAX_CV_TEXT]}")
    return "\n\n".join(parts) or "No candidate profile supplied; design for the job only."


def build_generation_prompt(job: dict[str, Any], profile: dict[str, Any] | None) -> str:
    description = _strip_html(job.get("description") or "")[:MAX_JOB_DESCRIPTION]
    locations = ", ".join(_json_list(job.get("locations_json"))) or "Unspecified"
    technologies = ", ".join(_json_list(job.get("technologies_json"))) or "Unspecified"

    return f"""JOB
Title: {job.get("title") or "Unspecified"}
Company: {job.get("company_name") or "Unspecified"}
Seniority: {job.get("seniority") or "Unspecified"}
Occupation: {job.get("occupation") or "Unspecified"}
Technologies: {technologies}
Locations: {locations}
Employment type: {job.get("employment_type") or "Unspecified"}
Workplace: {job.get("workplace_type") or "Unspecified"}
Description:
{description or "No description provided."}

CANDIDATE PROFILE
{_profile_text(profile)}

INSTRUCTIONS
- Choose only the sections that make sense for this job, seniority and role family.
- Use a realistic number of items per section (1-6) and 8-30 items in total.
- General and behavioural questions are usually useful; coding, SQL, system design and
  role-specific sections depend on the role.
- For software engineering roles include 2-5 LeetCode problems. For data roles,
  emphasise SQL exercises. Use canonical LeetCode URLs of the form
  https://leetcode.com/problems/<slug>/.
- Only include system design when the role and seniority justify it.
- multiple_choice items need 2-6 options, a correct_option_id and an explanation.
- text_response, debugging, code_reading, sql_exercise and scenario items need a
  rubric with 2-4 weighted criteria.
- external_practice items need a resource and activity evaluation.
- All section and item ids must be unique, lowercase letters, numbers and hyphens.
- Return only the JSON object described by the schema."""


def _slug(value: Any, fallback: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
    return text[:40] or fallback


def _unique(value: str, used: set[str]) -> str:
    candidate = value
    suffix = 2
    while candidate in used:
        candidate = f"{value[:36]}-{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _canonical_leetcode(url: str) -> str:
    parsed = urlparse(url)
    match = re.search(r"/problems/([a-z0-9-]+)", parsed.path.lower())
    return f"https://leetcode.com/problems/{match.group(1)}/" if match else url


def normalize_payload(payload: Any) -> dict[str, Any]:
    """Make model output a little more forgiving before Pydantic validates it."""
    if not isinstance(payload, dict):
        raise GenerationError("The model did not return a JSON object.")

    data = dict(payload)
    sections = data.get("sections")
    if not isinstance(sections, list):
        raise GenerationError("The model did not return any sections.")

    for key in ("difficulty", "relevance", "priority"):
        if isinstance(data.get(key), str):
            data[key] = data[key].lower()

    section_ids: set[str] = set()
    item_ids: set[str] = set()

    for section_index, section in enumerate(sections, start=1):
        if not isinstance(section, dict):
            raise GenerationError("A section was not a JSON object.")

        section["id"] = _unique(
            _slug(section.get("id"), f"section-{section_index}"), section_ids
        )
        if isinstance(section.get("priority"), str):
            section["priority"] = section["priority"].lower()
        if isinstance(section.get("type"), str):
            section["type"] = section["type"].lower()

        items = section.get("items")
        if not isinstance(items, list):
            items = []
        section["items"] = items

        for item_index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                raise GenerationError("An item was not a JSON object.")

            item["id"] = _unique(
                _slug(item.get("id"), f"{section['id']}-{item_index}"), item_ids
            )
            for key in ("type", "difficulty", "relevance"):
                if isinstance(item.get(key), str):
                    item[key] = item[key].lower()

            if item.get("options") is None:
                item["options"] = []
            for option_index, option in enumerate(item["options"], start=1):
                if isinstance(option, dict) and not option.get("id"):
                    option["id"] = chr(96 + option_index)

            if item.get("resource") is not None and isinstance(item["resource"], dict):
                provider = str(item["resource"].get("provider") or "").lower()
                if provider == "leetcode" and item["resource"].get("url"):
                    item["resource"]["url"] = _canonical_leetcode(
                        str(item["resource"]["url"])
                    )

            evaluation = item.get("evaluation")
            if isinstance(evaluation, dict):
                if isinstance(evaluation.get("method"), str):
                    evaluation["method"] = evaluation["method"].lower()
                if evaluation.get("rubric") is None:
                    evaluation["rubric"] = []

    return data


def _generate_valid_assessment(job: dict[str, Any], profile: dict[str, Any] | None) -> Assessment:
    prompt = build_generation_prompt(job, profile)
    last_error: Exception | None = None

    for attempt in range(2):
        try:
            payload = generate_json(
                input=prompt,
                system_instruction=SYSTEM_INSTRUCTION,
                schema=GENERATION_SCHEMA,
            )
            return Assessment.model_validate(normalize_payload(payload))
        except (ValidationError, GenerationError, json.JSONDecodeError) as exc:
            last_error = exc
            logger.warning("Interview assessment attempt %s was invalid: %s", attempt + 1, exc)

    raise GenerationError(
        "The model returned an invalid assessment. Please try again."
    ) from last_error


def generate_assessment(
    conn: psycopg.Connection,
    *,
    user_id: UUID,
    job_id: int,
    new_attempt: bool,
) -> tuple[UUID, bool]:
    """Return (attempt_id, created). Reuses the latest attempt unless asked for a new one."""
    lock_key = f"interview:{user_id}:{job_id}"
    conn.execute("SELECT pg_advisory_lock(hashtext(%s))", (lock_key,))
    conn.commit()

    try:
        if not new_attempt:
            existing = interview_store.latest_attempt(conn, user_id, job_id)
            if existing:
                return existing["id"], False

        job = interview_store.load_job(conn, job_id)
        if job is None:
            raise JobNotFound("Job not found.")
        profile = interview_store.load_profile(conn, user_id)
        conn.commit()

        assessment = _generate_valid_assessment(job, profile)
        internal = assessment.model_dump(mode="json")
        public = public_assessment(assessment)
        progress = compute_progress(assessment, [])

        with conn.transaction():
            if new_attempt:
                interview_store.supersede_active(conn, user_id, job_id)
            attempt_no = interview_store.next_attempt_no(conn, user_id, job_id)
            attempt_id = interview_store.insert_attempt(
                conn,
                user_id=user_id,
                job_id=job_id,
                attempt_no=attempt_no,
                title=assessment.title,
                role_family=assessment.role_family,
                assessment_internal=internal,
                assessment_public=public,
                progress=progress,
            )
        return attempt_id, True
    finally:
        conn.execute("SELECT pg_advisory_unlock(hashtext(%s))", (lock_key,))
        conn.commit()
