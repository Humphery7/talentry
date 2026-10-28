import asyncio
from uuid import uuid4

from schemas.agent import (
    AgentAction,
    AgentDecision,
    FormField,
    FormObservation,
    FormOption,
)
from schemas.browser import ActionResult
from services.agent_applications.agent import Agent
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
