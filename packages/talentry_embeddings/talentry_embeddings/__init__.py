"""The one place Talentry builds embedding text and runs the embedding model."""

from __future__ import annotations

import hashlib
import re
import threading
from collections.abc import Sequence

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMENSIONS = 384

MAX_JOB_DESCRIPTION = 4_000
MAX_CV_TEXT = 8_000

_model = None
_model_lock = threading.Lock()
_encode_lock = threading.Lock()


def _get_model():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from sentence_transformers import SentenceTransformer

                _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed_texts(texts: Sequence[str]) -> list[list[float]]:
    """Return one normalized 384-dimensional vector per text."""
    if not texts:
        return []

    model = _get_model()
    with _encode_lock:
        vectors = model.encode(
            list(texts),
            batch_size=32,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )

    return [[float(value) for value in vector] for vector in vectors]


def embed_text(text: str) -> list[float]:
    return embed_texts([text])[0]


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _strip_html(html: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text, flags=re.IGNORECASE)
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&quot;", '"')
    text = re.sub(r"&#39;|&apos;", "'", text)
    return re.sub(r"\s+", " ", text).strip()


def _add(parts: list[str], label: str, value: str | None) -> None:
    text = (value or "").strip()
    if text:
        parts.append(f"{label}: {text}")


def build_job_text(
    *,
    title: str | None,
    description: str | None,
    company_name: str | None = None,
    locations: Sequence[str] | None = None,
    employment_type: str | None = None,
    workplace_type: str | None = None,
    seniority: str | None = None,
    occupation: str | None = None,
    technologies: Sequence[str] | None = None,
) -> str:
    parts: list[str] = []

    _add(parts, "Job title", title)
    _add(parts, "Company", company_name)
    _add(parts, "Location", ", ".join(locations or []))
    _add(parts, "Workplace", workplace_type)
    _add(parts, "Employment type", employment_type)
    _add(parts, "Seniority", seniority)
    _add(parts, "Occupation", occupation.replace("-", " ") if occupation else None)
    _add(parts, "Technologies", ", ".join(technologies or []))

    if description:
        text = _strip_html(description)[:MAX_JOB_DESCRIPTION]
        if text:
            parts.append(f"Description:\n{text}")

    return "\n\n".join(parts)


def build_profile_text(
    *,
    headline: str | None,
    current_title: str | None,
    years_experience: int | None,
    location: str | None,
    summary: str | None,
    cv_text: str | None,
) -> str:
    parts: list[str] = []

    _add(parts, "Headline", headline)
    _add(parts, "Current title", current_title)
    if years_experience is not None:
        parts.append(f"Years of experience: {years_experience}")
    _add(parts, "Location", location)
    _add(parts, "Summary", summary)

    text = (cv_text or "").strip()
    if text:
        parts.append(f"CV:\n{text[:MAX_CV_TEXT]}")

    return "\n\n".join(parts)
