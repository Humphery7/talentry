"""Validation and public serialization for interview prep.

The model output is stored as one JSON document per attempt. Everything the
frontend is allowed to see passes through `public_assessment()`, which drops
answer keys, rubrics and explanations.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator

MAX_SERIALIZED_BYTES = 250_000
MAX_SECTIONS = 12
MAX_ITEMS_PER_SECTION = 12
MAX_TOTAL_ITEMS = 60
MAX_RESPONSE_TEXT = 20_000

_LEETCODE_HOSTS = {"leetcode.com", "www.leetcode.com"}
_LEETCODE_PATH = re.compile(r"^/problems/[a-z0-9-]+/?$")


class SectionType(str, Enum):
    general = "general"
    behavioural = "behavioural"
    coding = "coding"
    technical = "technical"
    role_specific = "role_specific"
    system_design = "system_design"
    other = "other"


class ItemType(str, Enum):
    text_response = "text_response"
    multiple_choice = "multiple_choice"
    external_practice = "external_practice"
    debugging = "debugging"
    code_reading = "code_reading"
    sql_exercise = "sql_exercise"
    scenario = "scenario"


class Difficulty(str, Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"


class Priority(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class EvaluationMethod(str, Enum):
    objective = "objective"
    llm_rubric = "llm_rubric"
    activity = "activity"


_WRITTEN_TYPES = {
    ItemType.text_response,
    ItemType.debugging,
    ItemType.code_reading,
    ItemType.sql_exercise,
    ItemType.scenario,
}


class Resource(BaseModel):
    provider: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=500)

    @field_validator("url")
    @classmethod
    def https_url(cls, value: str) -> str:
        parsed = urlparse(value.strip())
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("resource url must be an absolute https URL")
        if parsed.username or parsed.password:
            raise ValueError("resource url must not contain credentials")
        return value.strip()


class Option(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,12}$")
    text: str = Field(min_length=1, max_length=500)


class RubricCriterion(BaseModel):
    criterion: str = Field(min_length=1, max_length=200)
    weight: float = Field(gt=0, le=10)
    description: str = Field(min_length=1, max_length=500)


class Evaluation(BaseModel):
    method: EvaluationMethod
    correct_option_id: str | None = Field(default=None, max_length=12)
    explanation: str | None = Field(default=None, max_length=2000)
    rubric: list[RubricCriterion] = Field(default_factory=list, max_length=6)
    model_answer: str | None = Field(default=None, max_length=4000)

    @field_validator("rubric", mode="before")
    @classmethod
    def rubric_none_to_empty(cls, value: Any) -> Any:
        return [] if value is None else value


class Item(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,40}$")
    type: ItemType
    question: str = Field(min_length=1, max_length=2000)
    instructions: str | None = Field(default=None, max_length=1000)
    topic: str = Field(min_length=1, max_length=100)
    difficulty: Difficulty
    relevance: Priority
    estimated_minutes: int = Field(ge=1, le=180)
    options: list[Option] = Field(default_factory=list, max_length=6)
    resource: Resource | None = None
    evaluation: Evaluation

    @field_validator("options", mode="before")
    @classmethod
    def options_none_to_empty(cls, value: Any) -> Any:
        return [] if value is None else value

    @model_validator(mode="after")
    def check_type_requirements(self) -> "Item":
        if self.type == ItemType.multiple_choice:
            self._check_multiple_choice()
        elif self.type == ItemType.external_practice:
            self._check_external_practice()
        else:
            self._check_written()
        return self

    def _check_multiple_choice(self) -> None:
        if self.evaluation.method != EvaluationMethod.objective:
            raise ValueError("multiple_choice items need objective evaluation")
        if not 2 <= len(self.options) <= 6:
            raise ValueError("multiple_choice items need 2-6 options")
        if len({option.id for option in self.options}) != len(self.options):
            raise ValueError("option ids must be unique")
        if self.evaluation.correct_option_id not in {o.id for o in self.options}:
            raise ValueError("correct_option_id must match one of the options")
        if not self.evaluation.explanation:
            raise ValueError("multiple_choice items need an explanation")
        if self.resource is not None:
            raise ValueError("multiple_choice items cannot have a resource")

    def _check_external_practice(self) -> None:
        if self.evaluation.method != EvaluationMethod.activity:
            raise ValueError("external_practice items need activity evaluation")
        if self.resource is None:
            raise ValueError("external_practice items need a resource")
        if self.resource.provider.lower() == "leetcode":
            parsed = urlparse(self.resource.url)
            if parsed.hostname not in _LEETCODE_HOSTS or not _LEETCODE_PATH.match(
                parsed.path
            ):
                raise ValueError(
                    "LeetCode links must look like https://leetcode.com/problems/<slug>/"
                )
        if self.options:
            raise ValueError("external_practice items cannot have options")

    def _check_written(self) -> None:
        if self.evaluation.method != EvaluationMethod.llm_rubric:
            raise ValueError(f"{self.type.value} items need llm_rubric evaluation")
        if not self.evaluation.rubric:
            raise ValueError(
                f"{self.type.value} items need at least one rubric criterion"
            )
        if self.options:
            raise ValueError(f"{self.type.value} items cannot have options")
        if self.resource is not None:
            raise ValueError(f"{self.type.value} items cannot have a resource")


class Section(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,40}$")
    type: SectionType
    title: str = Field(min_length=1, max_length=120)
    priority: Priority
    description: str = Field(min_length=1, max_length=1000)
    estimated_minutes: int = Field(ge=1, le=300)
    items: list[Item] = Field(min_length=1, max_length=MAX_ITEMS_PER_SECTION)


class Assessment(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    role_family: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=1000)
    estimated_minutes: int = Field(ge=5, le=600)
    sections: list[Section] = Field(min_length=1, max_length=MAX_SECTIONS)

    @model_validator(mode="after")
    def check_ids_and_size(self) -> "Assessment":
        section_ids = [section.id for section in self.sections]
        if len(set(section_ids)) != len(section_ids):
            raise ValueError("section ids must be unique")

        item_ids = [item.id for section in self.sections for item in section.items]
        if len(set(item_ids)) != len(item_ids):
            raise ValueError("item ids must be unique across the assessment")
        if len(item_ids) > MAX_TOTAL_ITEMS:
            raise ValueError(
                f"assessment may contain at most {MAX_TOTAL_ITEMS} items"
            )

        size = len(self.model_dump_json().encode("utf-8"))
        if size > MAX_SERIALIZED_BYTES:
            raise ValueError("assessment is too large")
        return self


def find_item(assessment: Assessment, item_id: str) -> Item | None:
    for section in assessment.sections:
        for item in section.items:
            if item.id == item_id:
                return item
    return None


def _public_item(item: Item) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": item.id,
        "type": item.type.value,
        "question": item.question,
        "instructions": item.instructions,
        "topic": item.topic,
        "difficulty": item.difficulty.value,
        "relevance": item.relevance.value,
        "estimatedMinutes": item.estimated_minutes,
    }
    if item.options:
        data["options"] = [
            {"id": option.id, "text": option.text} for option in item.options
        ]
    if item.resource is not None:
        data["resource"] = {
            "provider": item.resource.provider,
            "title": item.resource.title,
            "url": item.resource.url,
        }
    return data


def public_assessment(assessment: Assessment) -> dict[str, Any]:
    """The safe copy stored alongside the internal one and returned to the UI."""
    return {
        "title": assessment.title,
        "roleFamily": assessment.role_family,
        "summary": assessment.summary,
        "estimatedMinutes": assessment.estimated_minutes,
        "sections": [
            {
                "id": section.id,
                "type": section.type.value,
                "title": section.title,
                "priority": section.priority.value,
                "description": section.description,
                "estimatedMinutes": section.estimated_minutes,
                "items": [_public_item(item) for item in section.items],
            }
            for section in assessment.sections
        ],
    }


def compute_progress(
    assessment: Assessment, responses: list[dict[str, Any]]
) -> dict[str, Any]:
    """Deterministic completion, section progress and (only at 100%) readiness."""
    by_item = {str(row["item_id"]): row for row in responses}
    sections: list[dict[str, Any]] = []
    total = 0
    completed = 0

    for section in assessment.sections:
        section_total = len(section.items)
        section_done = sum(
            1
            for item in section.items
            if bool(by_item.get(item.id, {}).get("completed"))
        )
        total += section_total
        completed += section_done
        sections.append(
            {
                "id": section.id,
                "completedItems": section_done,
                "totalItems": section_total,
                "percent": round(100 * section_done / section_total)
                if section_total
                else 0,
            }
        )

    percent = round(100 * completed / total) if total else 0
    readiness: int | None = None
    if percent == 100:
        scores = [
            int(row["score"]) for row in responses if row.get("score") is not None
        ]
        if scores:
            readiness = round(sum(scores) / len(scores))

    return {
        "totalItems": total,
        "completedItems": completed,
        "percent": percent,
        "readiness": readiness,
        "sections": sections,
    }
