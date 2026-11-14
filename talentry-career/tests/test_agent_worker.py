from services.agent_applications.agent import ActionError
from services.agent_applications.worker import explain


def test_captcha_is_explained_without_jargon():
    reason = explain(ActionError("CAPTCHA detected on the page"))
    assert "CAPTCHA" in reason
    assert "ActionError" not in reason


def test_timeout_is_explained_in_plain_words():
    assert explain(ActionError("Timeout 30000ms exceeded")) == (
        "The employer's site stopped responding."
    )


def test_network_failure_is_explained():
    reason = explain(ActionError("net::ERR_CONNECTION_REFUSED"))
    assert reason == "Talentry could not reach the employer's site."


def test_a_message_written_for_the_user_is_kept():
    message = "The employer site blocked automated access."
    assert explain(ActionError(message)) == message


def test_unknown_errors_get_a_calm_sentence():
    assert explain(ValueError("key 'foo' not found")) == (
        "Something went wrong while Talentry was filling in the form."
    )
