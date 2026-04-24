"""
Agent 基础工厂模块

提供 LLM 和 Embedding 实例工厂，统一从运行时设置读取模型配置，
允许用户在前端覆盖 API Key、Base URL 和模型名称。
"""

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.api.settings import get_runtime_setting
from app.core.config import settings as app_settings


def get_processing_llm() -> ChatOpenAI:
    """返回用于 Agent 处理（实体提取、锚点构建）的 LLM 实例。"""
    api_key = get_runtime_setting("openai_api_key", app_settings.OPENAI_API_KEY)
    base_url = get_runtime_setting("openai_base_url", app_settings.OPENAI_BASE_URL)
    model = get_runtime_setting("processing_model", app_settings.DEFAULT_PROCESSING_MODEL)

    return ChatOpenAI(
        model=model,
        api_key=api_key or "sk-placeholder",
        base_url=base_url or None,
        temperature=0,
        timeout=120,
    )


def get_chat_llm(model_override: str | None = None) -> ChatOpenAI:
    """返回用于 Chat Brain 对话的 LLM 实例，支持每次请求级别的模型覆盖。"""
    api_key = get_runtime_setting("openai_api_key", app_settings.OPENAI_API_KEY)
    base_url = get_runtime_setting("openai_base_url", app_settings.OPENAI_BASE_URL)
    model = model_override or get_runtime_setting("chat_model", app_settings.DEFAULT_CHAT_MODEL)

    return ChatOpenAI(
        model=model,
        api_key=api_key or "sk-placeholder",
        base_url=base_url or None,
        temperature=0.3,
        timeout=180,
        streaming=True,
    )


def get_embeddings() -> OpenAIEmbeddings:
    """返回用于生成文本向量的 Embedding 实例。"""
    api_key = get_runtime_setting("openai_api_key", app_settings.OPENAI_API_KEY)
    base_url = get_runtime_setting("openai_base_url", app_settings.OPENAI_BASE_URL)
    model = get_runtime_setting("embedding_model", app_settings.DEFAULT_EMBEDDING_MODEL)

    return OpenAIEmbeddings(
        model=model,
        openai_api_key=api_key or "sk-placeholder",
        openai_api_base=base_url or None,
    )
