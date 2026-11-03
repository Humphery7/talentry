from talentry_embeddings import (
    EMBEDDING_DIMENSIONS,
    build_job_text,
    build_profile_text,
    text_hash,
)


def test_job_text_matches_the_existing_format():
    text = build_job_text(
        title="Senior Frontend Engineer",
        description="<p>Build <strong>accessible</strong> web apps.</p>",
        company_name="Acme",
        locations=["Lagos", "Remote"],
        workplace_type="Remote",
        employment_type="Full time",
        seniority="senior",
        occupation="frontend-developer",
        technologies=["react", "typescript"],
    )

    assert text == (
        "Job title: Senior Frontend Engineer\n\n"
        "Company: Acme\n\n"
        "Location: Lagos, Remote\n\n"
        "Workplace: Remote\n\n"
        "Employment type: Full time\n\n"
        "Seniority: senior\n\n"
        "Occupation: frontend developer\n\n"
        "Technologies: react, typescript\n\n"
        "Description:\nBuild accessible web apps."
    )
    assert EMBEDDING_DIMENSIONS == 384


def test_job_text_leaves_out_missing_fields():
    assert build_job_text(title="Designer", description=None) == "Job title: Designer"


def test_profile_text_matches_the_existing_format():
    text = build_profile_text(
        headline=" Frontend Engineer ",
        current_title=None,
        years_experience=0,
        location="Lagos",
        summary=None,
        cv_text="Built design systems.",
    )

    assert text == (
        "Headline: Frontend Engineer\n\n"
        "Years of experience: 0\n\n"
        "Location: Lagos\n\n"
        "CV:\nBuilt design systems."
    )


def test_text_hash_changes_when_the_text_changes():
    assert text_hash("one") == text_hash("one")
    assert text_hash("one") != text_hash("two")
