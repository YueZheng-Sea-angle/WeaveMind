"""
Agent 基础工厂模块

提供 LLM 和 Embedding 实例工厂，统一从运行时设置读取模型配置，
允许用户在前端覆盖 API Key、Base URL 和模型名称。
"""

from __future__ import annotations

import httpx
import langchain_openai.chat_models.base as _lc_openai_base
from langchain.output_parsers import OutputFixingParser
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.output_parsers import BaseOutputParser
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.api.settings import get_runtime_setting
from app.core.config import settings as app_settings


# ── Thinking 模式兼容补丁 ─────────────────────────────────────────────────────
# DeepSeek / Anthropic 等 thinking 模型在流式多轮对话中要求将上一轮响应的
# reasoning_content 原样传回。LangChain 默认不处理该字段，此处通过 monkey-patch
# 让三个关键函数正确地捕获并传递 reasoning_content。

_orig_dict_to_msg = _lc_openai_base._convert_dict_to_message
_orig_delta_to_chunk = _lc_openai_base._convert_delta_to_message_chunk
_orig_msg_to_dict = _lc_openai_base._convert_message_to_dict


def _patched_dict_to_msg(d):
    """非流式响应：将 reasoning_content 存入 AIMessage.additional_kwargs。"""
    msg = _orig_dict_to_msg(d)
    if isinstance(msg, AIMessage) and (rc := d.get("reasoning_content")):
        msg.additional_kwargs["reasoning_content"] = rc
    return msg


def _patched_delta_to_chunk(d, default_class):
    """流式 delta：将 reasoning_content 存入 AIMessageChunk.additional_kwargs。
    merge_dicts 会将相邻 chunk 的字符串值自动拼接，完整还原思考过程。"""
    chunk = _orig_delta_to_chunk(d, default_class)
    if isinstance(chunk, AIMessageChunk) and (rc := d.get("reasoning_content")):
        chunk.additional_kwargs["reasoning_content"] = rc
    return chunk


def _patched_msg_to_dict(message):
    """消息转 API dict：若含 reasoning_content 则一并输出，满足多轮回传要求。"""
    d = _orig_msg_to_dict(message)
    if isinstance(message, AIMessage) and (
        rc := message.additional_kwargs.get("reasoning_content")
    ):
        d["reasoning_content"] = rc
    return d


_lc_openai_base._convert_dict_to_message = _patched_dict_to_msg
_lc_openai_base._convert_delta_to_message_chunk = _patched_delta_to_chunk
_lc_openai_base._convert_message_to_dict = _patched_msg_to_dict


def _make_async_http_client(read_timeout: float) -> httpx.AsyncClient:
    """创建带合理超时与连接池的 httpx 客户端，降低长流式请求断连概率。"""
    return httpx.AsyncClient(
        timeout=httpx.Timeout(
            connect=30.0,
            read=read_timeout,
            write=30.0,
            pool=30.0,
        ),
        limits=httpx.Limits(
            max_connections=20,
            max_keepalive_connections=10,
            keepalive_expiry=60.0,
        ),
    )


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


def get_card_builder_llm() -> ChatOpenAI:
    """返回用于「关键角色卡构建」Agent 的 LLM 实例。

    角色卡需要从整章正文中归纳结构化档案，质量敏感，因此独立于处理模型，
    允许用户单独指定更强（更贵）的模型。未单独配置时回退到处理模型的有效值，
    保证旧用户行为不变。
    """
    api_key = get_runtime_setting("openai_api_key", app_settings.OPENAI_API_KEY)
    base_url = get_runtime_setting("openai_base_url", app_settings.OPENAI_BASE_URL)
    # 未显式设置 card_model 时，回退到当前生效的 processing_model
    processing_model = get_runtime_setting(
        "processing_model", app_settings.DEFAULT_PROCESSING_MODEL
    )
    model = get_runtime_setting("card_model", processing_model)

    return ChatOpenAI(
        model=model,
        api_key=api_key or "sk-placeholder",
        base_url=base_url or None,
        temperature=0,
        timeout=180,
    )


def get_chat_llm(model_override: str | None = None) -> ChatOpenAI:
    """返回用于 Chat Brain 对话的 LLM 实例，支持每次请求级别的模型覆盖。

    优先使用对话大脑专属 API Key / Base URL；未单独配置时回退到主 API。
    """
    api_key = (
        get_runtime_setting("chat_api_key", app_settings.CHAT_API_KEY)
        or get_runtime_setting("openai_api_key", app_settings.OPENAI_API_KEY)
    )
    base_url = (
        get_runtime_setting("chat_base_url", app_settings.CHAT_BASE_URL)
        or get_runtime_setting("openai_base_url", app_settings.OPENAI_BASE_URL)
    )
    model = model_override or get_runtime_setting("chat_model", app_settings.DEFAULT_CHAT_MODEL)

    read_timeout = 300.0
    return ChatOpenAI(
        model=model,
        api_key=api_key or "sk-placeholder",
        base_url=base_url or None,
        temperature=0.3,
        timeout=read_timeout,
        max_retries=3,
        streaming=True,
        http_async_client=_make_async_http_client(read_timeout),
    )


def build_robust_parser(parser: BaseOutputParser, llm: ChatOpenAI) -> BaseOutputParser:
    """
    将结构化输出解析器包装为带自动纠错的解析器。

    当模型偶发返回不合规范的 JSON（例如回显 schema 本身）时，
    OutputFixingParser 会把原始输出与解析错误一并回传给模型，要求其修正为合法结果，
    从而避免单次解析失败导致整章分析报错。
    """
    return OutputFixingParser.from_llm(parser=parser, llm=llm, max_retries=2)


def get_embeddings() -> OpenAIEmbeddings:
    """返回用于生成文本向量的 Embedding 实例。
    
    优先使用 embedding 专属 API Key / Base URL；
    若未单独配置，则自动回退到主 API（openai_api_key / openai_base_url）。
    """
    # Embedding 专属 key，不存在时回退到主 API key
    api_key = (
        get_runtime_setting("embedding_api_key", app_settings.EMBEDDING_API_KEY)
        or get_runtime_setting("openai_api_key", app_settings.OPENAI_API_KEY)
    )
    # Embedding 专属 base_url，不存在时回退到主 API base_url
    base_url = (
        get_runtime_setting("embedding_base_url", app_settings.EMBEDDING_BASE_URL)
        or get_runtime_setting("openai_base_url", app_settings.OPENAI_BASE_URL)
    )
    model = get_runtime_setting("embedding_model", app_settings.DEFAULT_EMBEDDING_MODEL)

    return OpenAIEmbeddings(
        model=model,
        openai_api_key=api_key or "sk-placeholder",
        openai_api_base=base_url or None,
    )
