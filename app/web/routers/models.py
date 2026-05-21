from fastapi import APIRouter

from app.web.constants import CLIENTS, MODEL_LABELS
from app.web.services.chat_service import is_provider_configured


router = APIRouter(prefix="/api", tags=["models"])


@router.get("/models")
def list_models() -> list[dict[str, str | bool]]:
    return [
        {
            "provider": provider,
            "label": MODEL_LABELS[provider],
            "configured": is_provider_configured(provider),
        }
        for provider in CLIENTS
    ]
