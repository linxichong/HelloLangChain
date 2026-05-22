from http import HTTPStatus

from app.web.model_errors import ModelErrorCode, classify_model_error


class ProviderError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class BodyError(Exception):
    def __init__(self, body: dict) -> None:
        super().__init__("provider body error")
        self.body = body


def test_classifies_retryable_timeout() -> None:
    info = classify_model_error(TimeoutError("deadline exceeded"), provider="gemini")

    assert info.code == ModelErrorCode.TIMEOUT
    assert info.status_code == HTTPStatus.REQUEST_TIMEOUT
    assert info.retryable is True
    assert info.provider == "gemini"


def test_classifies_quota_from_error_body() -> None:
    info = classify_model_error(BodyError({"error": {"code": "insufficient_quota"}}))

    assert info.code == ModelErrorCode.INSUFFICIENT_QUOTA
    assert info.status_code == HTTPStatus.PAYMENT_REQUIRED


def test_unknown_error_message_is_sanitized() -> None:
    info = classify_model_error(RuntimeError("secret stack detail"))

    assert info.code == ModelErrorCode.UNKNOWN
    assert "secret stack detail" not in info.message


def test_classifies_status_code() -> None:
    info = classify_model_error(ProviderError("busy", HTTPStatus.TOO_MANY_REQUESTS))

    assert info.code == ModelErrorCode.RATE_LIMITED
    assert info.retryable is True
