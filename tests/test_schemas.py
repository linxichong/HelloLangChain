import pytest
from pydantic import ValidationError

from app.web.schemas import ChatRequest, CreateUserRequest, LoginRequest, RegisterRequest


def test_chat_request_normalizes_case_and_trims_text() -> None:
    request = ChatRequest(
        provider="Gemini",
        analysis_mode="AGENT",
        style="  concise  ",
        question="  hello  ",
    )

    assert request.provider == "gemini"
    assert request.analysis_mode == "agent"
    assert request.style == "concise"
    assert request.question == "hello"


def test_chat_request_rejects_empty_question_and_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ChatRequest(question="   ")

    with pytest.raises(ValidationError):
        ChatRequest(question="hello", unexpected=True)


def test_user_requests_validate_username_password_and_role() -> None:
    assert LoginRequest(username=" alice ", password="x").username == "alice"

    with pytest.raises(ValidationError):
        RegisterRequest(username="ab", password="12345678")

    with pytest.raises(ValidationError):
        RegisterRequest(username="alice smith", password="12345678")

    with pytest.raises(ValidationError):
        CreateUserRequest(username="alice", password="12345678", role="admin")
