import os
import time
from collections.abc import Iterator
from typing import Any

from app.agents.stock_agent import invoke_stock_agent
from app.chains.chat_chain import ChatResult, build_chat_chain, invoke_chat
from app.db import auth_store
from app.db.auth_store import AuthUser
from app.tools.financial_tools import build_financial_context
from app.web.constants import (
    CLIENTS,
    DEFAULT_STYLE,
    MAX_MODEL_RETRIES,
    MODEL_LABELS,
    PROVIDER_API_KEYS,
)
from app.web.model_errors import ModelCallError, classify_model_error
from app.web.schemas import ChatRequest, ChatResponse


def chat(request: ChatRequest, user: AuthUser) -> ChatResponse:
    provider = request.provider.lower()
    analysis_mode = normalize_analysis_mode(request.analysis_mode)
    question = request.question.strip()
    if not question:
        raise ValueError("问题不能为空")

    try:
        client = make_client(provider)
    except Exception as exc:
        raise ModelCallError(classify_model_error(exc, provider), exc) from exc

    inputs = {
        "role": request.role,
        "language": request.language,
        "style": (request.style or "").strip() or DEFAULT_STYLE,
        "question": question,
        "history": build_history(user, provider) if request.use_memory else "本轮不使用历史对话。",
        "financial_context": (
            build_financial_context(question)
            if analysis_mode == "standard"
            else "Agent 模式会按需调用金融数据工具。"
        ),
    }

    result = invoke_chat_with_retries(client, inputs, analysis_mode, provider)

    if request.use_memory:
        auth_store.append_memory(user, provider, "user", question)
        auth_store.append_memory(user, provider, "assistant", result.answer)

    return ChatResponse(
        provider=provider,
        provider_label=MODEL_LABELS.get(provider, provider),
        model=client.model,
        analysis_mode=analysis_mode,
        answer=result.answer,
        confidence=result.confidence,
    )


def make_client(provider: str):
    if provider not in CLIENTS:
        available = ", ".join(CLIENTS)
        raise ValueError(f"未知模型供应商：{provider}。可选值：{available}")
    return CLIENTS[provider]()


def is_provider_configured(provider: str) -> bool:
    api_key = PROVIDER_API_KEYS.get(provider)
    return api_key is None or bool(os.getenv(api_key))


def normalize_analysis_mode(value: str) -> str:
    mode = (value or "standard").lower()
    if mode in {"standard", "agent"}:
        return mode
    raise ValueError("未知分析模式。可选值：standard, agent")


def build_history(user: AuthUser, provider: str) -> str:
    messages = auth_store.get_history(user, provider)
    if not messages:
        return "暂无历史对话。"

    lines = []
    for message in messages:
        role = "用户" if message["role"] == "user" else "助手"
        lines.append(f"{role}：{message['content']}")
    return "\n".join(lines)


def invoke_chat_with_retries(
    client: Any,
    inputs: dict[str, Any],
    analysis_mode: str,
    provider: str,
) -> ChatResult:
    last_error: ModelCallError | None = None
    for attempt in range(MAX_MODEL_RETRIES + 1):
        try:
            if analysis_mode == "agent":
                return invoke_stock_agent(client, inputs)
            return invoke_chat(client, inputs)
        except Exception as exc:
            info = classify_model_error(exc, provider)
            last_error = ModelCallError(info, exc)
            if info.retryable and attempt < MAX_MODEL_RETRIES:
                time.sleep(1)
                continue
            raise last_error from exc

    if last_error is not None:
        raise last_error

    raise RuntimeError("模型调用失败。")


def stream_chat_events(
    request: ChatRequest,
    user: AuthUser,
) -> Iterator[dict[str, Any]]:
    provider = request.provider.lower()
    analysis_mode = normalize_analysis_mode(request.analysis_mode)
    question = request.question.strip()
    if not question:
        raise ValueError("问题不能为空")

    try:
        client = make_client(provider)
    except Exception as exc:
        raise ModelCallError(classify_model_error(exc, provider), exc) from exc

    inputs = build_chat_inputs(request, user, provider, analysis_mode, question)
    yield {
        "event": "start",
        "provider": provider,
        "analysis_mode": analysis_mode,
        "model": client.model,
    }

    if analysis_mode == "agent":
        result = invoke_chat_with_retries(client, inputs, analysis_mode, provider)
        yield {"event": "delta", "text": result.answer}
        save_memory_if_enabled(request, user, provider, question, result.answer)
        yield {
            "event": "done",
            "confidence": result.confidence,
            "analysis_mode": analysis_mode,
        }
        return

    answer = ""
    confidence = 0.0
    try:
        for chunk in build_chat_chain(client).stream(inputs):
            chunk_answer = chunk.get("answer")
            if chunk_answer and len(chunk_answer) > len(answer):
                delta = chunk_answer[len(answer) :]
                answer = chunk_answer
                yield {"event": "delta", "text": delta}

            if "confidence" in chunk and chunk["confidence"] is not None:
                confidence = float(chunk["confidence"])
    except Exception as exc:
        raise ModelCallError(classify_model_error(exc, provider), exc) from exc

    save_memory_if_enabled(request, user, provider, question, answer)
    yield {
        "event": "done",
        "confidence": confidence,
        "analysis_mode": analysis_mode,
    }


def build_chat_inputs(
    request: ChatRequest,
    user: AuthUser,
    provider: str,
    analysis_mode: str,
    question: str,
) -> dict[str, Any]:
    return {
        "role": request.role,
        "language": request.language,
        "style": (request.style or "").strip() or DEFAULT_STYLE,
        "question": question,
        "history": build_history(user, provider) if request.use_memory else "本轮不使用历史对话。",
        "financial_context": (
            build_financial_context(question)
            if analysis_mode == "standard"
            else "Agent 模式会按需调用金融数据工具。"
        ),
    }


def save_memory_if_enabled(
    request: ChatRequest,
    user: AuthUser,
    provider: str,
    question: str,
    answer: str,
) -> None:
    if not request.use_memory:
        return

    auth_store.append_memory(user, provider, "user", question)
    auth_store.append_memory(user, provider, "assistant", answer)
