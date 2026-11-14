import asyncio
from uuid import uuid4

from schemas.agent import (
    AgentAction,
    AgentDecision,
    FormField,
    FormObservation,
    FormOption,
)
from schemas.agent_applications import AttentionItem
from schemas.browser import ActionResult
from services.agent_applications.agent import Agent, FormChanged
from services.agent_applications import facts


class FakeTools:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    async def fill_field(self, element_id: str, value: str) -> ActionResult:
        self.calls.append(("fill", element_id, value))
        return ActionResult(ok=True, message="")

    async def select_option(self, element_id: str, value: str) -> ActionResult:
        self.calls.append(("select", element_id, value))
        return ActionResult(ok=True, message="")

    async def select_combobox(
        self, element_id: str, value: str
    ) -> ActionResult:
        self.calls.append(("combobox", element_id, value))
        return ActionResult(ok=True, message="")

    async def set_checked(
        self, element_id: str, checked: bool
    ) -> ActionResult:
        self.calls.append(("checked", element_id, str(checked)))
        return ActionResult(ok=True, message="")

    async def click_element(self, element_id: str) -> ActionResult:
        self.calls.append(("click", element_id, ""))
        return ActionResult(ok=True, message="")

    async def upload_file(self, element_id: str, path: object) -> ActionResult:
        self.calls.append(("upload", element_id, str(path)))
        return ActionResult(ok=True, message="")


def field(
    element_id: str,
    label: str,
    *,
    kind: str = "text",
    action: str = "fill",
    required: bool = False,
    value: str = "",
    section: str | None = None,
    options: list[FormOption] | None = None,
) -> FormField:
    return FormField(
        element_id=element_id,
        key=facts.normalize(label) + ":" + kind,
        label=label,
        kind=kind,
        action=action,
        required=required,
        value=value,
        section=section,
        options=options or [],
    )


def agent() -> Agent:
    value = Agent.__new__(Agent)
    value.app = {"id": uuid4()}
    value.conn = None
    value.session = None
    value.tools = FakeTools()
    value.user = {"name": "Ada Lovelace", "email": "ada@example.com"}
    value.profile = {"cv_data": "CV"}
    value.job = {"title": "Engineer"}
    value.bank = {}
    value.cv_text = "CV"
    value.facts = {
        "full_name": "Ada Lovelace",
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "ada@example.com",
    }
    value.fields = {}
    value.attention = []
    value.warnings = []
    value.options = {}
    value.applied = set()
    value.failures = {}
    value.pinned = {}
    value.clicked_submit = False
    value.feedback = []
    value._pdfs = {}
    return value


def test_deterministic_uses_profile_and_asks_for_sensitive() -> None:
    value = agent()
    name = field("name", "Full name", required=True)
    authorization = field(
        "auth",
        "Work authorization",
        kind="radio",
        action="radio",
        required=True,
        section="Work authorization",
    )
    phone = field("phone", "Phone", required=True)

    entry = value.deterministic(name)
    assert entry is not None
    assert entry.value == "Ada Lovelace"
    assert entry.source == "profile"

    assert value.deterministic(authorization) is None
    assert value.pending()[0].field_key == authorization.key
    assert value.pending()[0].sensitive is True
    assert value.pending()[0].category == "work authorization"

    assert value.deterministic(phone) is None
    assert value.pending()[-1].fact_key == "phone"


def test_saved_answer_beats_asking() -> None:
    value = agent()
    value.bank = {
        facts.normalize("Phone"): {
            "question": "Phone",
            "answer": "+1 555 0100",
        }
    }
    phone = field("phone", "Phone", required=True)

    entry = value.deterministic(phone)

    assert entry is not None
    assert entry.value == "+1 555 0100"
    assert entry.status == "saved"
    assert value.pending() == []


def test_settle_fills_known_fields_and_leaves_choices_for_the_model() -> None:
    value = agent()
    name = field("name", "Full name", required=True)
    email = field("email", "Email", required=True)
    country = field(
        "country",
        "Country",
        kind="select",
        action="select",
        required=False,
        options=[
            FormOption(value="us", label="United States"),
            FormOption(value="ca", label="Canada"),
        ],
    )
    observation = FormObservation(
        url="https://example.com",
        title="Form",
        text="",
        fields=[name, email, country],
    )

    todo = asyncio.run(value.settle(observation))

    assert todo == [country]
    assert value.tools.calls == [
        ("fill", "name", "Ada Lovelace"),
        ("fill", "email", "ada@example.com"),
    ]
    assert value.fields[name.key].status == "filled"
    assert value.fields[email.key].status == "filled"

    decision = AgentDecision(
        actions=[AgentAction(type="skip", element_id="country")]
    )
    feedback, progressed = asyncio.run(
        value.execute(decision, todo, observation)
    )
    assert feedback == []
    assert progressed is True
    assert value.fields[country.key].status == "skipped"


def test_submit_settle_never_fills_new_fields() -> None:
    value = agent()
    unexpected = field("new", "New required field", required=True)
    observation = FormObservation(
        url="https://example.com",
        title="Form",
        text="",
        fields=[unexpected],
    )

    todo = asyncio.run(value.settle(observation, only_approved=True))

    assert todo == [unexpected]
    assert value.tools.calls == []
    assert value.fields == {}


def test_site_reformatted_value_is_kept() -> None:
    value = agent()
    location = field("loc", "Current location")
    entry = value.entry(location, "Lagos, Nigeria", "user", "user")
    value.fields[location.key] = entry

    changed = field("loc", "Current location", value="Lagos, Lagos, Nigeria")

    assert value.adopt_site_value(changed, entry) is True
    assert entry.value == "Lagos, Lagos, Nigeria"
    assert value.warnings


def test_different_value_is_not_adopted() -> None:
    value = agent()
    location = field("loc", "Current location")
    entry = value.entry(location, "Lagos, Nigeria", "user", "user")
    value.fields[location.key] = entry

    changed = field("loc", "Current location", value="Abuja, Nigeria")

    assert value.adopt_site_value(changed, entry) is False
    assert entry.value == "Lagos, Nigeria"
    assert value.warnings == []


def test_manual_notes_do_not_block_approval() -> None:
    from services.agent_applications.store import open_questions

    attention = [
        {"kind": "manual", "answer": None},
        {"kind": "question", "answer": "Lagos"},
    ]

    assert open_questions(attention) == []
    assert open_questions([{"kind": "question", "answer": None}]) == [
        {"kind": "question", "answer": None}
    ]


def test_saved_sensitive_answer_is_never_reused() -> None:
    value = agent()
    value.bank = {
        "q:salary expectation": {
            "question": "Salary expectation",
            "answer": "50000",
        }
    }
    salary = field("salary", "Salary expectation", required=True)

    assert value.deterministic(salary) is None
    assert value.pending()[-1].sensitive is True


def test_an_answer_is_reused_when_the_site_renames_the_field() -> None:
    value = agent()
    value.attention = [
        AttentionItem(
            id="salary",
            kind="question",
            field_key="salary:number",
            label="Salary expectation",
            question="What should I put for “Salary expectation”?",
            answer="45000",
        )
    ]
    renamed = field("salary-2", "Salary expectation", required=True)

    entry = value.user_or_saved(renamed)

    assert entry is not None
    assert entry.value == "45000"
    assert entry.status == "user"


def test_a_plan_entry_survives_a_changed_field_key() -> None:
    value = agent()
    old = field("old-key", "Current company", required=True)
    value.fields[old.key] = value.entry(old, "Glovo", "user", "user")

    renamed = field("new-key", "Current company", required=True)
    observation = FormObservation(
        url="https://example.com",
        title="Form",
        text="",
        fields=[renamed],
    )

    todo = asyncio.run(value.settle(observation))

    assert todo == []
    assert value.tools.calls == [("fill", "new-key", "Glovo")]


def test_the_same_question_is_only_asked_once() -> None:
    value = agent()
    phone = field("phone", "Phone", required=True)

    value.ask(phone, "Your profile does not have a phone.", fact_key="phone")
    value.ask(phone, "I could not determine this answer.")

    questions = [item for item in value.attention if item.kind == "question"]
    assert len(questions) == 1
    assert questions[0].label == "Phone"


def test_a_new_style_saved_answer_is_found_by_its_label() -> None:
    value = agent()
    value.bank = {
        "q:current company": {
            "question": "What should I put for “Current company”?",
            "answer": "Glovo",
        }
    }
    company = field("company-9", "Current company", required=True)

    entry = value.user_or_saved(company)

    assert entry is not None
    assert entry.value == "Glovo"
    assert entry.status == "saved"


class SubmitPage(FakeTools):
    """A submit page that loads with empty fields.

    Real sites render the form first, then the values arrive. Filling is what
    puts them there, so a read taken before the fill sees nothing.
    """

    def __init__(self, *, keep_values: bool = True) -> None:
        super().__init__()
        self.keep_values = keep_values
        self.values: dict[str, str] = {}

    async def fill_field(self, element_id: str, value: str) -> ActionResult:
        if self.keep_values:
            self.values[element_id] = value
        return await super().fill_field(element_id, value)


def submit_page(tools: SubmitPage) -> FormObservation:
    first = field("first-name", "First Name", required=True)
    first.value = tools.values.get("first-name", "")
    return FormObservation(
        url="https://example.com/apply",
        title="Apply",
        text="",
        fields=[first],
    )


def approved_name(value: Agent) -> None:
    name = field("first-name", "First Name", required=True)
    value.fields[name.key] = value.entry(
        name, "Ufuoma-oghene", "user", "user"
    )


def test_submit_reads_the_page_back_after_filling() -> None:
    value = agent()
    tools = SubmitPage()
    value.tools = tools
    approved_name(value)

    async def read() -> FormObservation:
        return submit_page(tools)

    value._read = read  # type: ignore[method-assign]

    observation = asyncio.run(value._settle_and_verify())

    # Filled once, and the value that was verified is the freshly read one.
    assert tools.calls == [("fill", "first-name", "Ufuoma-oghene")]
    assert observation.fields[0].value == "Ufuoma-oghene"


def test_submit_still_stops_if_the_site_keeps_the_field_empty() -> None:
    value = agent()
    tools = SubmitPage(keep_values=False)
    value.tools = tools
    approved_name(value)

    async def read() -> FormObservation:
        return submit_page(tools)

    value._read = read  # type: ignore[method-assign]

    try:
        asyncio.run(value._settle_and_verify())
    except FormChanged as exc:
        assert "First Name" in str(exc)
    else:
        raise AssertionError("a field the site never accepted must stop submit")
