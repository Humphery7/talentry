from schemas.browser import ElementInfo, OptionInfo, PageInspection, PageSignals
from services.agent_applications import facts
from services.agent_applications.form import build_observation


def element(**kwargs) -> ElementInfo:
    return ElementInfo(**kwargs)


def test_form_groups_radios_and_separates_buttons() -> None:
    inspection = PageInspection(
        url="https://example.com/apply",
        title="Apply",
        text="Application form",
        ready_state="complete",
        errors=["Please fix this"],
        signals=PageSignals(captcha=True),
        elements=[
            element(
                id="name",
                tag="input",
                type="text",
                label="Full name",
                name="name",
                required=True,
                value="Ada Lovelace",
            ),
            element(
                id="email",
                tag="input",
                type="email",
                label="Email",
                name="email",
            ),
            element(
                id="auth-yes",
                tag="input",
                type="radio",
                label="Yes",
                name="authorized",
                value="yes",
                required=True,
                section="Work authorization",
            ),
            element(
                id="auth-no",
                tag="input",
                type="radio",
                label="No",
                name="authorized",
                value="no",
                section="Work authorization",
            ),
            element(
                id="remote",
                tag="div",
                role="radio",
                label="Remote",
                name="workplace",
            ),
            element(
                id="office",
                tag="div",
                role="radio",
                label="Office",
                name="workplace",
                checked=True,
            ),
            element(
                id="remote-input",
                tag="input",
                type="checkbox",
                label="Remote",
                name="remote",
                checked=True,
            ),
            element(
                id="remote-label",
                tag="label",
                type="checkbox",
                label="Remote",
                text="Remote",
                checked=True,
            ),
            element(
                id="country",
                tag="select",
                label="Country",
                name="country",
                required=True,
                value="us",
                options=[
                    OptionInfo(value="us", label="United States"),
                    OptionInfo(value="ca", label="Canada"),
                ],
            ),
            element(
                id="cv",
                tag="input",
                type="file",
                label="CV",
                name="cv",
                accept=".pdf",
                required=True,
            ),
            element(
                id="letter",
                tag="textarea",
                label="Cover letter",
                name="cover_letter",
                maxlength=500,
            ),
            element(id="next", tag="button", text="Next"),
            element(
                id="submit",
                tag="button",
                text="Submit application",
            ),
            element(id="apply", tag="a", text="Apply for this job"),
            element(id="site", tag="a", text="Company site"),
        ],
    )

    observation = build_observation(inspection)

    assert observation.errors == ["Please fix this"]
    assert observation.signals.captcha is True
    assert [field.label for field in observation.fields] == [
        "Full name",
        "Email",
        "Work authorization",
        "workplace",
        "Remote",
        "Country",
        "CV",
        "Cover letter",
    ]

    name, email, authorized, workplace, remote, country, cv, letter = (
        observation.fields
    )
    assert name.value == "Ada Lovelace"
    assert authorized.kind == "radio"
    assert authorized.action == "radio"
    assert authorized.required is True
    assert [option.label for option in authorized.options] == ["Yes", "No"]
    assert authorized.sensitive is True
    assert workplace.action == "click"
    assert workplace.value == "Office"
    assert remote.kind == "checkbox"
    assert remote.action == "checkbox"
    assert remote.value == "yes"
    assert country.options[0].label == "United States"
    assert country.value == "us"
    assert cv.action == "upload"
    assert letter.maxlength == 500
    assert [field.pos for field in observation.fields] == sorted(
        field.pos for field in observation.fields
    )

    assert [(button.text, button.is_submit) for button in observation.buttons] == [
        ("Next", False),
        ("Submit application", True),
        ("Apply for this job", False),
        ("Company site", False),
    ]


def test_form_names_duplicate_fields_and_skips_buttons() -> None:
    inspection = PageInspection(
        url="https://example.com",
        title="Form",
        text="",
        ready_state="complete",
        elements=[
            element(id="a", tag="input", type="text", label="Role"),
            element(id="b", tag="input", type="text", label="Role"),
            element(id="c", tag="button", text="Continue"),
        ],
    )

    observation = build_observation(inspection)

    assert [field.key for field in observation.fields] == [
        "role:text",
        "role:text#2",
    ]
    assert observation.buttons[0].is_submit is False


def test_facts_are_conservative() -> None:
    assert facts.fact_for_label("E-mail address") == "email"
    assert facts.fact_for_label("Current employer") == "current_company"
    assert facts.classify("Are you authorized to work here?") == (
        "work authorization"
    )
    assert facts.classify("Expected salary") == "compensation"
    assert facts.classify("First name") is None
    assert facts.is_personal_label("LinkedIn URL") is True
    assert facts.ungrounded_numbers(
        "Increased revenue 42% and served 1,200 users.",
        "Increased revenue and served users.",
    ) == ["1,200", "42%"]


def test_readiness_requires_cv_and_positioning() -> None:
    assert facts.readiness(None) == [
        "Upload your CV in your profile.",
        "Add a headline, current title or summary to your profile.",
    ]
    assert facts.readiness(
        {
            "cv_data": "CV",
            "headline": "Engineer",
        }
    ) == []
