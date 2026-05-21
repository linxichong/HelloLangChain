import asyncio

from fastapi import APIRouter, Depends, HTTPException

from app.db import auth_store
from app.db.auth_store import AuthUser
from app.web.dependencies import get_current_user
from app.web.schemas import ChatRequest, ChatResponse
from app.web.services.chat_service import chat


router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat_api(
    request: ChatRequest,
    user: AuthUser = Depends(get_current_user),
) -> ChatResponse:
    try:
        return await asyncio.to_thread(chat, request, user)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc


@router.post("/reset")
def reset_memory(user: AuthUser = Depends(get_current_user)) -> dict[str, bool]:
    auth_store.clear_memory(user)
    return {"ok": True}
