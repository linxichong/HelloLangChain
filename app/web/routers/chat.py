import asyncio
import json
import logging
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.db import auth_store
from app.db.auth_store import AuthUser
from app.web.dependencies import get_current_user
from app.web.model_errors import ModelCallError, error_response_detail
from app.web.schemas import ChatRequest, ChatResponse
from app.web.services.chat_service import chat, stream_chat_events


router = APIRouter(prefix="/api", tags=["chat"])
logger = logging.getLogger(__name__)

INTERNAL_ERROR_DETAIL = {
    "code": "internal_error",
    "message": "服务暂时异常，请稍后重试。",
    "retryable": False,
}


@router.post("/chat", response_model=ChatResponse)
async def chat_api(
    request: ChatRequest,
    user: AuthUser = Depends(get_current_user),
) -> ChatResponse:
    try:
        return await asyncio.to_thread(chat, request, user)
    except ModelCallError as exc:
        if exc.info.status_code >= 500:
            logger.exception("Chat model call failed")
        raise HTTPException(
            status_code=exc.info.status_code,
            detail=error_response_detail(exc.info),
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Chat request failed")
        raise HTTPException(
            status_code=500,
            detail=INTERNAL_ERROR_DETAIL,
        ) from exc


@router.post("/chat/stream")
def chat_stream_api(
    request: ChatRequest,
    user: AuthUser = Depends(get_current_user),
) -> StreamingResponse:
    return StreamingResponse(
        encode_stream_events(request, user),
        media_type="application/x-ndjson",
    )


@router.post("/reset")
def reset_memory(user: AuthUser = Depends(get_current_user)) -> dict[str, bool]:
    auth_store.clear_memory(user)
    return {"ok": True}


def encode_stream_events(
    request: ChatRequest,
    user: AuthUser,
) -> Iterator[str]:
    try:
        for event in stream_chat_events(request, user):
            yield json.dumps(event, ensure_ascii=False) + "\n"
    except ModelCallError as exc:
        if exc.info.status_code >= 500:
            logger.exception("Streaming chat model call failed")
        yield (
            json.dumps(
                {
                    "event": "error",
                    "detail": error_response_detail(exc.info),
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    except ValueError as exc:
        yield (
            json.dumps(
                {
                    "event": "error",
                    "detail": str(exc),
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    except Exception:
        logger.exception("Streaming chat request failed")
        yield (
            json.dumps(
                {
                    "event": "error",
                    "detail": INTERNAL_ERROR_DETAIL,
                },
                ensure_ascii=False,
            )
            + "\n"
        )
