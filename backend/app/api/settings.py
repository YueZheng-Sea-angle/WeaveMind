from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings as app_settings

router = APIRouter()


class ModelSettings(BaseModel):
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    anthropic_api_key: str | None = None
    processing_model: str | None = None
    verifier_model: str | None = None
    chat_model: str | None = None
    embedding_model: str | None = None


_runtime_settings: dict = {}


@router.get("")
async def get_settings():
    return {
        "processing_model": _runtime_settings.get(
            "processing_model", app_settings.DEFAULT_PROCESSING_MODEL
        ),
        "verifier_model": _runtime_settings.get(
            "verifier_model", app_settings.DEFAULT_VERIFIER_MODEL
        ),
        "chat_model": _runtime_settings.get("chat_model", app_settings.DEFAULT_CHAT_MODEL),
        "embedding_model": _runtime_settings.get(
            "embedding_model", app_settings.DEFAULT_EMBEDDING_MODEL
        ),
        "has_openai_key": bool(
            _runtime_settings.get("openai_api_key") or app_settings.OPENAI_API_KEY
        ),
        "has_anthropic_key": bool(
            _runtime_settings.get("anthropic_api_key") or app_settings.ANTHROPIC_API_KEY
        ),
    }


@router.put("")
async def update_settings(payload: ModelSettings):
    for field, value in payload.model_dump(exclude_none=True).items():
        _runtime_settings[field] = value
    return {"ok": True}


def get_runtime_setting(key: str, default: str) -> str:
    return _runtime_settings.get(key, default)
