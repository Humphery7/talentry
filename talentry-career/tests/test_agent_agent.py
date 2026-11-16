import asyncio
from uuid import uuid4

from schemas.agent import (
    AgentAction,
    AgentDecision,
    FormButton,
    FormField,
    FormObservation,
    FormOption,
    PageSignals,
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


class PhonePage(FakeTools):
    """A site that reformats phone numbers as soon as they are typed."""

    def __init__(self, formatted: str = "+234 906 563 7151") -> None:
        super().__init__()
        self.formatted = formatted
        self.value = ""

    async def fill_field(self, element_id: str, value: str) -> ActionResult:
        if element_id == "phone":
            self.value = self.formatted
        return await super().fill_field(element_id, value)


def phone_observation(tools: PhonePage) -> FormObservation:
    phone = field("phone", "Phone", kind="tel", required=True)
    phone.value = tools.value
    return FormObservation(
        url="https://example.com/apply",
        title="Apply",
        text="",
        fields=[phone],
    )


def approved_phone(value: Agent) -> None:
    phone = field("phone", "Phone", kind="tel", required=True)
    value.fields[phone.key] = value.entry(
        phone, "+2349065637151", "profile", "filled"
    )


def test_site_phone_formatting_is_not_a_different_answer() -> None:
    value = agent()
    phone = field("phone", "Phone", kind="tel", required=True)
    phone.value = "+234 906 563 7151"
    entry = value.entry(phone, "+2349065637151", "profile", "filled")

    assert value.matches(phone, entry) is True


def test_a_genuinely_different_phone_is_still_a_change() -> None:
    value = agent()
    phone = field("phone", "Phone", kind="tel", required=True)
    phone.value = "+234 906 563 7152"
    entry = value.entry(phone, "+2349065637151", "profile", "filled")

    assert value.matches(phone, entry) is False


def test_submit_accepts_a_phone_the_site_reformatted() -> None:
    value = agent()
    tools = PhonePage()
    value.tools = tools
    approved_phone(value)

    async def read() -> FormObservation:
        return phone_observation(tools)

    value._read = read  # type: ignore[method-assign]

    observation = asyncio.run(value._settle_and_verify())

    assert tools.calls == [("fill", "phone", "+2349065637151")]
    assert observation.fields[0].value == "+234 906 563 7151"


def test_submit_stops_when_the_site_shows_a_different_phone() -> None:
    value = agent()
    tools = PhonePage(formatted="+234 906 563 7152")
    value.tools = tools
    approved_phone(value)

    async def read() -> FormObservation:
        return phone_observation(tools)

    value._read = read  # type: ignore[method-assign]

    try:
        asyncio.run(value._settle_and_verify())
    except FormChanged as exc:
        assert "Phone" in str(exc)
    else:
        raise AssertionError("a different phone number must stop submit")


# --- read_outcome: emailed verification codes and honest hand-offs ---------


def greenhouse_observation() -> FormObservation:
    """The AI Squared / Greenhouse page after the submit click."""
    code = field("code", "Security code")
    return FormObservation(
        url="https://job-boards.greenhouse.io/aisquared/jobs/4604010006",
        title="Machine Learning Engineer",
        text=(
            "A verification code was sent to ada@example.com. To submit your "
            "application, enter the 8-character code to confirm you’re a "
            "human."
        ),
        fields=[code],
    )


class Shot:
    """Stand-in for BrowserSession.screenshot_jpeg()."""

    async def screenshot_jpeg(self) -> bytes:
        return b"jpeg"


def code_challenge_with_button() -> FormObservation:
    """The challenge page once the submit button is visible."""
    return FormObservation(
        url=greenhouse_observation().url,
        title="Machine Learning Engineer",
        text=greenhouse_observation().text,
        fields=[field("code", "Security code")],
        buttons=[
            FormButton(
                element_id="code-submit",
                text="Submit application",
                kind="button",
                is_submit=True,
            )
        ],
    )


def plain_form_observation() -> FormObservation:
    return FormObservation(
        url="https://example.com/apply",
        title="Apply",
        text="Tell us about yourself, then submit your application.",
        fields=[field("name", "Full name")],
    )


def test_verification_code_page_is_detected() -> None:
    from services.agent_applications.agent import _verification_challenge

    assert _verification_challenge(greenhouse_observation()) is True
    assert _verification_challenge(plain_form_observation()) is False
    # A postal-code validation error must not look like a code challenge.
    postal = FormObservation(
        url="https://example.com/apply",
        title="Apply",
        text="Enter a valid postal code.",
        fields=[field("postal", "Postal code")],
    )
    assert _verification_challenge(postal) is False


def test_code_submit_button_ignores_resend() -> None:
    from services.agent_applications.agent import _code_submit_button

    observation = code_challenge_with_button().model_copy(
        update={
            "buttons": [
                FormButton(
                    element_id="resend",
                    text="Resend code",
                    kind="button",
                ),
                FormButton(
                    element_id="code-submit",
                    text="Submit application",
                    kind="button",
                    is_submit=True,
                ),
            ]
        }
    )
    picked = _code_submit_button(observation)
    assert picked is not None and picked.element_id == "code-submit"

    # If resending is the only button, there is nothing to submit with: the
    # user must be asked again rather than have the page re-mailed at them.
    only_resend = observation.model_copy(
        update={"buttons": [observation.buttons[0]]}
    )
    assert _code_submit_button(only_resend) is None


def test_read_outcome_holds_the_page_and_submits_the_code(
    monkeypatch,
) -> None:
    from services.agent_applications import agent as module

    value = agent()
    finished: dict[str, object] = {}
    held: dict[str, object] = {}
    observations = [
        greenhouse_observation(),
        code_challenge_with_button(),
        FormObservation(
            url="https://job-boards.greenhouse.io/thanks",
            title="Thanks",
            text="Thank you for applying.",
            fields=[],
            signals=PageSignals(confirmation=True),
        ),
    ]

    class Tools(FakeTools):
        async def inspect_page(self) -> object:
            return object()  # build_observation is patched below

        async def allow_submit(self) -> None:
            self.calls.append(("allow", "", ""))

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(module.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(
        module,
        "build_observation",
        lambda _inspection: observations.pop(0),
    )
    monkeypatch.setattr(
        module.store,
        "hold_for_code",
        lambda conn, app, plan, attention, shot=None: held.update(
            plan=plan, attention=attention
        ),
    )
    monkeypatch.setattr(
        module.store,
        "code_state",
        lambda conn, app: {
            "status": "awaiting_code",
            "attention": [{"kind": "code", "answer": "12345678"}],
        },
    )
    monkeypatch.setattr(module.store, "touch", lambda *a, **k: None)
    monkeypatch.setattr(module.store, "notify", lambda *a, **k: None)
    monkeypatch.setattr(module.store, "refresh_attention", lambda *a, **k: [])
    monkeypatch.setattr(module.store, "checkpoint", lambda *a, **k: None)
    monkeypatch.setattr(
        module.store,
        "finish",
        lambda conn, app, status, **cols: finished.update(
            status=status, **cols
        ),
    )
    monkeypatch.setattr(module.store, "event", lambda *a, **k: None)
    value.tools = Tools()
    value.session = Shot()

    assert asyncio.run(value.read_outcome()) == "submitted"
    assert held["attention"][0]["kind"] == "code"
    assert ("fill", "code", "12345678") in value.tools.calls
    assert ("click", "code-submit", "") in value.tools.calls
    assert finished["status"] == "submitted"
    assert finished["attention"] == []


def test_read_outcome_hands_off_when_there_is_no_code_box(monkeypatch) -> None:
    from services.agent_applications import agent as module

    value = agent()
    finished: dict[str, object] = {}
    human_check = FormObservation(
        url="https://example.com/apply",
        title="Apply",
        text="Please confirm you’re a human before continuing.",
        fields=[],
    )

    class Tools:
        async def inspect_page(self) -> object:
            return object()

    class Shot:
        async def screenshot_jpeg(self) -> bytes:
            return b"jpeg"

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(module.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(module, "build_observation", lambda _i: human_check)
    monkeypatch.setattr(
        module.store,
        "finish",
        lambda conn, app, status, **cols: finished.update(status=status, **cols),
    )
    monkeypatch.setattr(module.store, "event", lambda *a, **k: None)
    value.tools = Tools()
    value.session = Shot()

    assert asyncio.run(value.read_outcome()) == "unconfirmed"
    assert finished["status"] == "unconfirmed"
    assert finished["result"]["outcome"] == "verification_code"
    assert "It went through" in str(finished["error"])


def test_read_outcome_closes_the_page_when_no_code_is_entered(
    monkeypatch,
) -> None:
    from services.agent_applications import agent as module

    value = agent()
    finished: dict[str, object] = {}

    class Tools:
        async def inspect_page(self) -> object:
            return object()

    class Shot:
        async def screenshot_jpeg(self) -> bytes:
            return b"jpeg"

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(module.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(
        module, "build_observation", lambda _i: greenhouse_observation()
    )
    monkeypatch.setattr(module.store, "hold_for_code", lambda *a, **k: None)
    monkeypatch.setattr(module.store, "notify", lambda *a, **k: None)
    monkeypatch.setattr(module.settings, "AGENT_CODE_WAIT_SECONDS", 0)
    monkeypatch.setattr(module.store, "refresh_attention", lambda *a, **k: [])
    monkeypatch.setattr(module.store, "checkpoint", lambda *a, **k: None)
    monkeypatch.setattr(
        module.store,
        "finish",
        lambda conn, app, status, **cols: finished.update(status=status, **cols),
    )
    monkeypatch.setattr(module.store, "event", lambda *a, **k: None)
    value.tools = Tools()
    value.session = Shot()

    assert asyncio.run(value.read_outcome()) == "unconfirmed"
    assert finished["result"]["outcome"] == "code_timeout"
    assert "none was entered in time" in str(finished["error"])
    assert "Copy my details" in str(finished["error"])


def test_read_outcome_says_the_form_was_not_accepted(monkeypatch) -> None:
    from services.agent_applications import agent as module

    value = agent()
    finished: dict[str, object] = {}

    class Tools:
        async def inspect_page(self) -> object:
            return object()

    class Shot:
        async def screenshot_jpeg(self) -> bytes:
            return b"jpeg"

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(module.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(
        module,
        "build_observation",
        lambda _inspection: plain_form_observation(),
    )
    monkeypatch.setattr(
        module.store,
        "finish",
        lambda conn, app, status, **cols: finished.update(
            status=status, **cols
        ),
    )
    monkeypatch.setattr(module.store, "event", lambda *args, **kwargs: None)
    value.tools = Tools()
    value.session = Shot()

    assert asyncio.run(value.read_outcome()) == "unconfirmed"
    assert finished["result"]["outcome"] == "form_still_present"
    assert "did not accept" in str(finished["error"])
    assert "It went through" in str(finished["error"])


def test_read_outcome_admits_it_cannot_confirm_without_claiming_failure(
    monkeypatch,
) -> None:
    from schemas.agent import FormObservation
    from services.agent_applications import agent as module

    value = agent()
    finished: dict[str, object] = {}
    gone = FormObservation(
        url="https://example.com/thanks",
        title="Thanks",
        text="Thank you for your interest.",
        fields=[],
    )

    class Tools:
        async def inspect_page(self) -> object:
            return object()

    class Shot:
        async def screenshot_jpeg(self) -> bytes:
            return b"jpeg"

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(module.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(module, "build_observation", lambda _i: gone)
    monkeypatch.setattr(
        module.store,
        "finish",
        lambda conn, app, status, **cols: finished.update(
            status=status, **cols
        ),
    )
    monkeypatch.setattr(module.store, "event", lambda *args, **kwargs: None)
    value.tools = Tools()
    value.session = Shot()

    assert asyncio.run(value.read_outcome()) == "unconfirmed"
    assert finished["result"]["outcome"] == "no_confirmation"
    assert "probably went through" in str(finished["error"])


def test_verification_code_is_detected_even_without_a_visible_field() -> None:
    from schemas.agent import FormObservation
    from services.agent_applications.agent import _verification_challenge

    # Some sites put the code input inside an iframe the inspector cannot see.
    observation = FormObservation(
        url="https://example.com/verify",
        title="Verify",
        text="A verification code was sent to ada@example.com.",
        fields=[],
    )

    assert _verification_challenge(observation) is True


def test_wrong_code_is_asked_again_instead_of_sent_for_review(
    monkeypatch,
) -> None:
    from services.agent_applications import agent as module

    value = agent()
    finished: dict[str, object] = {}
    rejected = greenhouse_observation().model_copy(
        update={"errors": ["That code is invalid."]}
    )

    class Tools:
        async def inspect_page(self) -> object:
            return object()

    class Shot:
        async def screenshot_jpeg(self) -> bytes:
            return b"jpeg"

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(module.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(module, "build_observation", lambda _i: rejected)
    monkeypatch.setattr(
        module.store,
        "finish",
        lambda conn, app, status, **cols: finished.update(status=status),
    )
    monkeypatch.setattr(module.store, "event", lambda *a, **k: None)
    value.tools = Tools()
    value.session = Shot()

    # After a code is entered the page still asking means "try again", not
    # "the employer rejected your application".
    assert asyncio.run(value.read_outcome(allow_code=False)) == "challenge"
    assert finished == {}
