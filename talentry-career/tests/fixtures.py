from __future__ import annotations

from copy import deepcopy
from typing import Any


def assessment_payload() -> dict[str, Any]:
    return {
        "title": "Backend Engineer Interview Prep",
        "role_family": "software-engineering",
        "summary": "A balanced prep set for a backend role.",
        "estimated_minutes": 45,
        "sections": [
            {
                "id": "s1",
                "type": "behavioural",
                "title": "Behavioural",
                "priority": "high",
                "description": "How you work with others.",
                "estimated_minutes": 15,
                "items": [
                    {
                        "id": "s1-q1",
                        "type": "text_response",
                        "question": "Tell me about a time you disagreed with a teammate.",
                        "topic": "conflict",
                        "difficulty": "medium",
                        "relevance": "high",
                        "estimated_minutes": 5,
                        "evaluation": {
                            "method": "llm_rubric",
                            "rubric": [
                                {
                                    "criterion": "Clarity",
                                    "weight": 2,
                                    "description": "Explains the situation and their role.",
                                },
                                {
                                    "criterion": "Outcome",
                                    "weight": 1,
                                    "description": "Ends with a concrete result.",
                                },
                            ],
                        },
                    }
                ],
            },
            {
                "id": "s2",
                "type": "technical",
                "title": "Technical",
                "priority": "high",
                "description": "Core concepts.",
                "estimated_minutes": 15,
                "items": [
                    {
                        "id": "s2-q1",
                        "type": "multiple_choice",
                        "question": "Which SQL clause filters groups?",
                        "topic": "sql",
                        "difficulty": "easy",
                        "relevance": "high",
                        "estimated_minutes": 3,
                        "options": [
                            {"id": "a", "text": "HAVING"},
                            {"id": "b", "text": "WHERE"},
                            {"id": "c", "text": "ORDER BY"},
                        ],
                        "evaluation": {
                            "method": "objective",
                            "correct_option_id": "a",
                            "explanation": "HAVING filters after aggregation.",
                        },
                    }
                ],
            },
            {
                "id": "s3",
                "type": "coding",
                "title": "Coding",
                "priority": "medium",
                "description": "Practice problems.",
                "estimated_minutes": 15,
                "items": [
                    {
                        "id": "s3-q1",
                        "type": "external_practice",
                        "question": "Solve Two Sum.",
                        "topic": "arrays",
                        "difficulty": "easy",
                        "relevance": "high",
                        "estimated_minutes": 15,
                        "resource": {
                            "provider": "leetcode",
                            "title": "Two Sum",
                            "url": "https://leetcode.com/problems/two-sum/",
                        },
                        "evaluation": {"method": "activity"},
                    }
                ],
            },
        ],
    }


def fixed_payload() -> dict[str, Any]:
    return deepcopy(assessment_payload())
