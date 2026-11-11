from __future__ import annotations

from services.agent_applications import facts


def test_profile_contact_fields_become_facts() -> None:
    result = facts.build_facts(
        {"name": "Ada Example", "email": "ada@example.com"},
        {
            "location": "Lagos, Nigeria",
            "phone": "+1 555 0100",
            "linkedin_url": "https://linkedin.com/in/ada",
            "github_url": "https://github.com/ada",
            "website_url": "https://ada.dev",
        },
        {},
    )

    assert result["phone"] == "+1 555 0100"
    assert result["linkedin_url"] == "https://linkedin.com/in/ada"
    assert result["github_url"] == "https://github.com/ada"
    assert result["website_url"] == "https://ada.dev"


def test_profile_wins_over_a_previously_saved_answer() -> None:
    result = facts.build_facts(
        {"name": "Ada Example", "email": "ada@example.com"},
        {"phone": "+1 555 0100"},
        {
            "fact:phone": {"answer": "+1 555 9999"},
            "fact:current_company": {"answer": "Acme"},
        },
    )

    assert result["phone"] == "+1 555 0100"
    assert result["current_company"] == "Acme"
