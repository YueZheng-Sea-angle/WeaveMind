"""
Chat Brain Agent

基于 LangGraph ReAct 架构实现的主对话大脑，支持：
  - 23 个工具调用（知识检索、实体查询、章节原文、时间线、实体增删改、关系增删改、锚点编辑、关键角色卡增删改等）
  - 多轮对话历史加载
  - SSE 流式文本输出
  - 工具调用链路事件推送（tool_start / tool_end）
  - 对话结束后自动将助手消息写入数据库
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator

import httpx
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from app.agents.base import get_chat_llm
from app.db.database import AsyncSessionLocal
from app.models.conversation import Message
from app.tools.chat_tools import make_tools

logger = logging.getLogger(__name__)

_MAX_CHAT_ATTEMPTS = 3
_AGENT_RECURSION_LIMIT = 50

TRANSIENT_LLM_ERRORS: tuple[type[BaseException], ...] = (
    httpx.RemoteProtocolError,
    httpx.ReadTimeout,
    httpx.ConnectError,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    httpx.ConnectTimeout,
    asyncio.TimeoutError,
    ConnectionError,
    BrokenPipeError,
)


def _is_transient_llm_error(exc: BaseException) -> bool:
    """判断是否为可重试的瞬时网络 / 流式断连错误。"""
    if isinstance(exc, TRANSIENT_LLM_ERRORS):
        return True
    cause = exc.__cause__
    return isinstance(cause, TRANSIENT_LLM_ERRORS)


def _format_chat_error(exc: BaseException) -> str:
    """将底层异常转换为用户可理解的提示。"""
    if isinstance(exc, httpx.RemoteProtocolError) or (
        isinstance(exc.__cause__, httpx.RemoteProtocolError)
    ):
        return (
            "API 流式连接被提前关闭（incomplete chunked read），"
            "通常由网络波动、代理超时或模型服务商限流引起。"
            "请直接重试；若频繁出现，可尝试更换模型或 API 线路。"
        )
    if isinstance(exc, (httpx.ReadTimeout, httpx.ConnectTimeout)) or isinstance(
        exc.__cause__, (httpx.ReadTimeout, httpx.ConnectTimeout)
    ):
        return "API 请求超时，请稍后重试或检查网络连接。"
    if isinstance(exc, httpx.ConnectError) or isinstance(exc.__cause__, httpx.ConnectError):
        return "无法连接到 API 服务，请检查 Base URL 与网络。"
    return f"对话处理出错：{exc}"


_SYSTEM_PROMPT = """你是 ReadAgent，一个专为长篇小说分析与理解而设计的智能助手。
你拥有以下工具来访问书籍的结构化知识库：

- search_knowledge：语义检索实体和章节摘要
- get_entity：查询实体详情；支持名称/别名模糊匹配，多个候选时按精确度排序返回
- get_chapter_anchor：获取指定章节的摘要、关键事件、出场人物、伏笔和主题词
- get_chapter_text：获取指定章节的完整原文（章节过长会截断，需逐行精读时改用 get_chapter_lines）
- get_chapter_lines：获取指定章节某一行数范围的原文（行号从 1 开始，用于精确定位与逐行引用）
- get_timeline：获取章节范围内的事件时间线
- get_entity_relations：获取某个实体的所有关系
- search_chapters：搜索相关章节的原文片段
- create_entity：新建实体（指定名称、类型、描述、别名、属性、首次出场章节）
- edit_entity：修改实体信息（描述、别名、类型、属性）
- delete_entity：删除实体及其全部关系（不可逆）
- edit_anchor：修改章节锚点（摘要、关键事件、伏笔、主题词）
- create_relation：在两个已有实体之间新建一条有向关系（起点 → 终点，指定关系类型、描述、章节范围）
- edit_relation：修改两实体之间已有关系的类型、描述或章节范围
- delete_relation：删除两实体之间的一条关系（不可逆，不影响实体本身）
- list_character_cards：列出本书所有「关键角色卡」概览（重点角色的结构化档案）
- get_character_card：获取某角色卡详情，按分类（生平/性格特点/人物关系/技能/道具/当前状态/关键伏笔）列出条目
- create_character_card：为某个重点角色新建角色卡
- edit_character_card：修改角色卡的角色名称或简介
- delete_character_card：删除角色卡及其全部条目（不可逆）
- add_character_card_entry：向角色卡某分类下新增一条子条目
- edit_character_card_entry：修改角色卡中某条子条目的标题或正文
- delete_character_card_entry：删除角色卡中的一条子条目（不可逆）

回答原则：
1. 优先调用工具获取准确信息，不依赖训练时的记忆
2. 当问题涉及具体细节时，主动使用多个工具进行多跳推理
3. 引用工具结果时，说明信息来源（如"根据第X章锚点"）
4. 对于编辑类请求，执行前先确认要修改的内容，执行后反馈修改结果
5. 新建前应先确认对象尚不存在（create_entity / create_relation / create_character_card）；删除属于不可逆操作（delete_entity / delete_relation / delete_character_card / delete_character_card_entry），执行前务必向用户确认
6. 操作关系（create/edit/delete_relation）前，建议先用 get_entity_relations 查看现有关系，避免重复或误删；当两实体间存在多条关系时，需用 match_relation_type 指定具体关系
7. 关于关键角色卡：你只能看到「启用中」的角色卡与条目，被用户停用的内容对你完全不可见；角色卡及条目的启用/停用状态由用户掌控，你无权查看或修改该状态，请勿尝试启用、停用或讨论某条目的开关状态
8. 使用中文回答，语气专业但友好"""


def _sse(event: str, data: dict) -> str:
    """格式化为 SSE 消息字符串。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _to_lc_messages(history: list[dict[str, Any]]) -> list:
    """将数据库消息历史转换为 LangChain 消息对象列表。"""
    messages = []
    for msg in history:
        role = msg.get("role", "")
        content = msg.get("content") or ""
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
    return messages


def _extract_text_from_content(content: Any) -> str:
    """从 LLM chunk / message content 中提取纯文本。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts)
    return ""


def _append_text(full_content: str, text: str) -> str:
    """追加文本，避免重复拼接 on_chat_model_end 已流式输出的内容。"""
    if not text:
        return full_content
    if full_content.endswith(text):
        return full_content
    if text.startswith(full_content):
        return text
    return full_content + text


async def chat_stream(
    book_id: int,
    conversation_id: int,
    history: list[dict[str, Any]],
    user_message: str,
    model: str | None = None,
) -> AsyncGenerator[str, None]:
    """
    运行 Chat Brain Agent 并以 SSE 格式流式输出事件。

    SSE 事件类型：
        text        - LLM 文本片段，data: {"chunk": str}
        tool_start  - 工具调用开始，data: {"tool_name": str, "input": dict}
        tool_end    - 工具调用结束，data: {"tool_name": str, "output": str}
        done        - 对话完成，data: {"message": "完成"}
        error       - 发生错误，data: {"message": str}

    生成器耗尽后自动将完整助手消息持久化到数据库。
    """
    llm = get_chat_llm(model)
    model_name = getattr(llm, "model_name", None) or getattr(llm, "model", "unknown")
    tools = make_tools(book_id)
    agent = create_react_agent(llm, tools)

    lc_messages = [SystemMessage(content=_SYSTEM_PROMPT)]
    lc_messages.extend(_to_lc_messages(history))
    lc_messages.append(HumanMessage(content=user_message))

    logger.info(
        "Chat 开始 book=%d conv=%d model=%s history=%d 用户: %s",
        book_id,
        conversation_id,
        model_name,
        len(history),
        user_message[:200] + ("…" if len(user_message) > 200 else ""),
    )

    full_content = ""
    tool_calls_log: list[dict[str, Any]] = []
    error_occurred = False
    stream_chunk_count = 0
    agent_completed = False
    last_exc: BaseException | None = None

    agent_config = {"recursion_limit": _AGENT_RECURSION_LIMIT}

    for attempt in range(1, _MAX_CHAT_ATTEMPTS + 1):
        full_content = ""
        tool_calls_log = []
        stream_chunk_count = 0
        agent_completed = False
        last_exc = None

        try:
            async for event in agent.astream_events(
                {"messages": lc_messages},
                config=agent_config,
                version="v1",
            ):
                kind: str = event.get("event", "")
                name: str = event.get("name", "")

                if kind == "on_chat_model_stream":
                    chunk = event["data"].get("chunk")
                    if chunk is None:
                        continue

                    reasoning = chunk.additional_kwargs.get("reasoning_content")
                    if reasoning:
                        logger.debug("LLM reasoning chunk: %s", reasoning[:500])

                    text = _extract_text_from_content(chunk.content)
                    if text:
                        stream_chunk_count += 1
                        full_content += text
                        logger.debug("LLM text chunk[%d]: %r", stream_chunk_count, text)
                        yield _sse("text", {"chunk": text})

                elif kind == "on_chat_model_end":
                    output = event["data"].get("output")
                    if output is None:
                        continue
                    end_text = _extract_text_from_content(getattr(output, "content", ""))
                    reasoning = getattr(output, "additional_kwargs", {}).get("reasoning_content")
                    if reasoning:
                        logger.debug(
                            "LLM reasoning (end): %s",
                            reasoning[:500] + ("…" if len(reasoning) > 500 else ""),
                        )
                    if end_text and end_text not in full_content:
                        delta = end_text[len(full_content) :] if end_text.startswith(full_content) else end_text
                        if delta:
                            logger.info(
                                "LLM 非流式补全 text (+%d chars): %s",
                                len(delta),
                                delta[:300] + ("…" if len(delta) > 300 else ""),
                            )
                            full_content = _append_text(full_content, end_text)
                            yield _sse("text", {"chunk": delta})

                elif kind == "on_tool_start":
                    raw_input = event["data"].get("input", {})
                    if isinstance(raw_input, str):
                        try:
                            parsed_input = json.loads(raw_input)
                        except json.JSONDecodeError:
                            parsed_input = {"raw": raw_input}
                    else:
                        parsed_input = raw_input or {}

                    tool_calls_log.append({"name": name, "input": parsed_input})
                    logger.info("工具调用开始: %s  input=%s", name, json.dumps(parsed_input, ensure_ascii=False)[:500])
                    yield _sse("tool_start", {"tool_name": name, "input": parsed_input})

                elif kind == "on_tool_end":
                    raw_output = event["data"].get("output", "")
                    output_str = (
                        str(raw_output) if not isinstance(raw_output, str) else raw_output
                    )
                    logger.info(
                        "工具调用结束: %s  output=%s",
                        name,
                        output_str[:500] + ("…" if len(output_str) > 500 else ""),
                    )
                    yield _sse(
                        "tool_end",
                        {"tool_name": name, "output": output_str[:1000]},
                    )

            agent_completed = True
            break

        except Exception as exc:
            last_exc = exc
            # 仅首轮、且尚未向前端推送任何事件时自动重试，避免重复 tool/text SSE
            can_retry = (
                attempt < _MAX_CHAT_ATTEMPTS
                and _is_transient_llm_error(exc)
                and len(tool_calls_log) == 0
                and stream_chunk_count == 0
            )

            if can_retry:
                logger.warning(
                    "Chat 瞬时错误，准备重试 book=%d conv=%d attempt=%d/%d tools=%d: %s",
                    book_id,
                    conversation_id,
                    attempt,
                    _MAX_CHAT_ATTEMPTS,
                    len(tool_calls_log),
                    exc,
                )
                await asyncio.sleep(min(2 ** (attempt - 1), 4))
                continue

            logger.error(
                "Chat Brain 运行时错误（book_id=%d conv=%d attempt=%d）：%s",
                book_id,
                conversation_id,
                attempt,
                exc,
                exc_info=True,
            )
            error_occurred = True
            yield _sse("error", {"message": _format_chat_error(exc)})
            break

    # ── 持久化助手消息（必须在 done 之前，否则前端 refetch 拿不到新消息）──
    if agent_completed and (full_content or tool_calls_log):
        try:
            async with AsyncSessionLocal() as db:
                msg = Message(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=full_content or None,
                    tool_calls=tool_calls_log,
                )
                db.add(msg)
                await db.commit()
            logger.info(
                "Chat 完成 book=%d conv=%d text=%d chars tools=%d 回复: %s",
                book_id,
                conversation_id,
                len(full_content),
                len(tool_calls_log),
                full_content[:500] + ("…" if len(full_content) > 500 else ""),
            )
        except Exception as exc:
            logger.error(
                "助手消息持久化失败（conv_id=%d）：%s",
                conversation_id,
                exc,
                exc_info=True,
            )
    elif agent_completed and not error_occurred:
        logger.warning(
            "Chat 空回复 book=%d conv=%d model=%s chunks=%d tools=%d 用户: %s",
            book_id,
            conversation_id,
            model_name,
            stream_chunk_count,
            len(tool_calls_log),
            user_message[:200],
        )
        yield _sse("error", {"message": "模型未返回任何内容，请重试或检查 API 配置"})
    elif error_occurred and last_exc is not None:
        logger.info(
            "Chat 中断，未持久化不完整回复 book=%d conv=%d text=%d tools=%d",
            book_id,
            conversation_id,
            len(full_content),
            len(tool_calls_log),
        )

    if agent_completed and not error_occurred:
        yield _sse("done", {"message": "完成"})
