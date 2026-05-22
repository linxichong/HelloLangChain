from dataclasses import dataclass
from enum import StrEnum
from http import HTTPStatus
from typing import Any


class ModelErrorCode(StrEnum):
    MISSING_API_KEY = "missing_api_key"
    INVALID_API_KEY = "invalid_api_key"
    INSUFFICIENT_QUOTA = "insufficient_quota"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    AGENT_STEP_LIMIT = "agent_step_limit"
    MODEL_UNAVAILABLE = "model_unavailable"
    BAD_REQUEST = "bad_request"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ModelErrorInfo:
    code: ModelErrorCode
    status_code: int
    message: str
    provider: str | None = None
    retryable: bool = False


class ModelCallError(RuntimeError):
    def __init__(self, info: ModelErrorInfo, original: Exception | None = None) -> None:
        super().__init__(info.message)
        self.info = info
        self.original = original


def classify_model_error(exc: Exception, provider: str | None = None) -> ModelErrorInfo:
    status_code = _get_status_code(exc)
    error_code = _get_error_code(exc)
    text = str(exc).lower()

    if _looks_like_missing_key(text):
        return ModelErrorInfo(
            code=ModelErrorCode.MISSING_API_KEY,
            status_code=HTTPStatus.BAD_REQUEST,
            message="模型 API key 未配置，请先在环境变量或 .env 中配置对应的 key。",
            provider=provider,
        )

    if _looks_like_timeout(exc, text):
        return ModelErrorInfo(
            code=ModelErrorCode.TIMEOUT,
            status_code=HTTPStatus.REQUEST_TIMEOUT,
            message="模型服务请求超时，请稍后重试。",
            provider=provider,
            retryable=True,
        )

    if _looks_like_agent_step_limit(exc, text):
        return ModelErrorInfo(
            code=ModelErrorCode.AGENT_STEP_LIMIT,
            status_code=HTTPStatus.REQUEST_TIMEOUT,
            message="Agent 已达到最大工具调用步骤数，请缩小问题范围或改用普通模式。",
            provider=provider,
        )

    if error_code == "insufficient_quota" or "insufficient_quota" in text:
        return ModelErrorInfo(
            code=ModelErrorCode.INSUFFICIENT_QUOTA,
            status_code=HTTPStatus.PAYMENT_REQUIRED,
            message="当前模型账号额度不足，请检查余额、账单或项目额度。",
            provider=provider,
        )

    if status_code == HTTPStatus.UNAUTHORIZED or _looks_like_invalid_key(text):
        return ModelErrorInfo(
            code=ModelErrorCode.INVALID_API_KEY,
            status_code=HTTPStatus.UNAUTHORIZED,
            message="模型 API key 无效或没有权限，请检查 key 是否正确、是否属于当前项目。",
            provider=provider,
        )

    if status_code == HTTPStatus.TOO_MANY_REQUESTS:
        return ModelErrorInfo(
            code=ModelErrorCode.RATE_LIMITED,
            status_code=HTTPStatus.TOO_MANY_REQUESTS,
            message="模型服务请求过于频繁，请稍后重试。",
            provider=provider,
            retryable=True,
        )

    if status_code in {
        HTTPStatus.BAD_GATEWAY,
        HTTPStatus.SERVICE_UNAVAILABLE,
        HTTPStatus.GATEWAY_TIMEOUT,
    }:
        return ModelErrorInfo(
            code=ModelErrorCode.MODEL_UNAVAILABLE,
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            message="模型服务暂时不可用，请稍后重试或切换模型。",
            provider=provider,
            retryable=True,
        )

    if status_code == HTTPStatus.NOT_FOUND or _looks_like_model_missing(text):
        return ModelErrorInfo(
            code=ModelErrorCode.MODEL_UNAVAILABLE,
            status_code=HTTPStatus.BAD_REQUEST,
            message="模型名称不可用或当前账号无权使用该模型，请检查模型配置。",
            provider=provider,
        )

    if status_code == HTTPStatus.BAD_REQUEST:
        return ModelErrorInfo(
            code=ModelErrorCode.BAD_REQUEST,
            status_code=HTTPStatus.BAD_REQUEST,
            message="模型请求参数无效，请检查输入、模型名称或上下文长度。",
            provider=provider,
        )

    return ModelErrorInfo(
        code=ModelErrorCode.UNKNOWN,
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        message="模型调用失败，请稍后重试或切换模型。",
        provider=provider,
    )


def error_response_detail(info: ModelErrorInfo) -> dict[str, Any]:
    return {
        "code": info.code,
        "message": info.message,
        "provider": info.provider,
        "retryable": info.retryable,
    }


def _get_status_code(exc: Exception) -> int | None:
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return status_code

    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if isinstance(status_code, int):
        return status_code

    return None


def _get_error_code(exc: Exception) -> str | None:
    code = getattr(exc, "code", None)
    if isinstance(code, str):
        return code

    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict) and isinstance(error.get("code"), str):
            return error["code"]
        if isinstance(body.get("code"), str):
            return body["code"]

    return None


def _looks_like_missing_key(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "请先设置环境变量",
            "missing credentials",
            "api key not found",
            "no api key",
        )
    )


def _looks_like_invalid_key(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "invalid api key",
            "incorrect api key",
            "permission denied",
            "invalid authentication",
            "authentication failed",
        )
    )


def _looks_like_timeout(exc: Exception, text: str) -> bool:
    return "timeout" in type(exc).__name__.lower() or any(
        marker in text
        for marker in (
            "timed out",
            "timeout",
            "deadline exceeded",
        )
    )


def _looks_like_model_missing(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "model_not_found",
            "model not found",
            "does not exist",
            "not found for api version",
            "not supported",
        )
    )


def _looks_like_agent_step_limit(exc: Exception, text: str) -> bool:
    return "recursion" in type(exc).__name__.lower() or any(
        marker in text
        for marker in (
            "recursion limit",
            "recursion_limit",
            "maximum number of steps",
            "max iterations",
        )
    )
