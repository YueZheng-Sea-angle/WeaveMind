"""
运行时设置接口

允许用户在前端直接覆盖 .env 中的 API Key / Base URL / 模型选择。
优先级：运行时设置 > .env 默认值

设置会持久化到 data/runtime_settings.json，重启后仍然生效。
敏感字段（API Key）在 GET 时只返回是否已配置，不返回原文。
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings as app_settings

router = APIRouter()


# ── 持久化 ────────────────────────────────────────────────────────────────────

_DATA_DIR = Path("data")
_SETTINGS_FILE = _DATA_DIR / "runtime_settings.json"
_lock = threading.Lock()


def _load() -> dict[str, Any]:
    if not _SETTINGS_FILE.exists():
        return {}
    try:
        with _SETTINGS_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data: dict[str, Any]) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _SETTINGS_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


_runtime_settings: dict[str, Any] = _load()


# ── Schemas ──────────────────────────────────────────────────────────────────

# 敏感字段：GET 时只返回是否已设置，不返回原文
_SENSITIVE_KEYS = {"openai_api_key", "anthropic_api_key", "embedding_api_key"}

# 允许写入的字段白名单（防止越权写入）
_ALLOWED_KEYS = {
    "openai_api_key",
    "openai_base_url",
    "anthropic_api_key",
    "processing_model",
    "verifier_model",
    "chat_model",
    "embedding_model",
    "embedding_api_key",
    "embedding_base_url",
}


class ModelSettings(BaseModel):
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    anthropic_api_key: str | None = None
    processing_model: str | None = None
    verifier_model: str | None = None
    chat_model: str | None = None
    embedding_model: str | None = None
    embedding_api_key: str | None = None
    embedding_base_url: str | None = None


class ResetRequest(BaseModel):
    keys: list[str] | None = None  # None 表示清空全部


# ── Routes ───────────────────────────────────────────────────────────────────


@router.get("")
async def get_settings() -> dict[str, Any]:
    """返回当前生效配置（运行时覆盖优先，否则使用 .env 默认值）。

    敏感字段（API Key）不回传原文，仅返回 has_xxx 布尔以及来源。
    """
    with _lock:
        rt = dict(_runtime_settings)

    # 非敏感字段：直接回显当前生效值
    def _effective(key: str, env_default: str) -> str:
        return rt.get(key) or env_default

    return {
        "openai_base_url": _effective("openai_base_url", app_settings.OPENAI_BASE_URL),
        "processing_model": _effective("processing_model", app_settings.DEFAULT_PROCESSING_MODEL),
        "verifier_model": _effective("verifier_model", app_settings.DEFAULT_VERIFIER_MODEL),
        "chat_model": _effective("chat_model", app_settings.DEFAULT_CHAT_MODEL),
        "embedding_model": _effective("embedding_model", app_settings.DEFAULT_EMBEDDING_MODEL),
        "embedding_base_url": _effective("embedding_base_url", app_settings.EMBEDDING_BASE_URL),
        # 敏感字段：只暴露状态
        "has_openai_key": bool(rt.get("openai_api_key") or app_settings.OPENAI_API_KEY),
        "has_anthropic_key": bool(rt.get("anthropic_api_key") or app_settings.ANTHROPIC_API_KEY),
        "has_embedding_key": bool(rt.get("embedding_api_key") or app_settings.EMBEDDING_API_KEY),
        # 配置来源（user / env / none），便于前端展示
        "openai_key_source": _source("openai_api_key", app_settings.OPENAI_API_KEY, rt),
        "anthropic_key_source": _source("anthropic_api_key", app_settings.ANTHROPIC_API_KEY, rt),
        "openai_base_url_source": _source("openai_base_url", app_settings.OPENAI_BASE_URL, rt),
        "embedding_key_source": _source("embedding_api_key", app_settings.EMBEDDING_API_KEY, rt),
        "embedding_base_url_source": _source("embedding_base_url", app_settings.EMBEDDING_BASE_URL, rt),
        # 运行时覆盖列表（不含值），便于前端展示哪些字段已被用户覆盖
        "user_overrides": sorted(rt.keys()),
    }


def _source(key: str, env_default: str, rt: dict[str, Any]) -> str:
    if rt.get(key):
        return "user"
    if env_default:
        return "env"
    return "none"


@router.put("")
async def update_settings(payload: ModelSettings) -> dict[str, Any]:
    """部分更新运行时设置。空字符串表示清除对应字段，回退到 .env。"""
    updates = payload.model_dump(exclude_unset=True)

    with _lock:
        for field, value in updates.items():
            if field not in _ALLOWED_KEYS:
                continue
            if value is None or value == "":
                _runtime_settings.pop(field, None)
            else:
                _runtime_settings[field] = value
        _save(_runtime_settings)

    return await get_settings()


@router.post("/reset")
async def reset_settings(payload: ResetRequest | None = None) -> dict[str, Any]:
    """重置指定字段（或全部）为 .env 默认值。"""
    keys = payload.keys if payload and payload.keys else None

    with _lock:
        if keys is None:
            _runtime_settings.clear()
        else:
            for key in keys:
                _runtime_settings.pop(key, None)
        _save(_runtime_settings)

    return await get_settings()


# ── Helpers (Agent 工厂使用) ─────────────────────────────────────────────────


def get_runtime_setting(key: str, default: str) -> str:
    """供 Agent 工厂调用：优先取用户运行时设置，否则取 .env 默认值。"""
    with _lock:
        return _runtime_settings.get(key) or default


# 显式导出，防止误用 _SENSITIVE_KEYS
__all__ = ["router", "get_runtime_setting"]
