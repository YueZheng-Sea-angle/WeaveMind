"""
Chat Brain Agent

基于 LangGraph ReAct 架构实现的主对话大脑，支持：
  - 8 个工具调用（知识检索、实体查询、时间线、编辑等）
  - 多轮对话历史加载
  - SSE 流式文本输出
  - 工具调用链路事件推送（tool_start / tool_end）
  - 对话结束后自动将助手消息写入数据库
"""

import asyncio
import json
import logging
from typing import Any, AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from app.agents.base import get_chat_llm
from app.db.database import AsyncSessionLocal
from app.models.conversation import Message
from app.tools.chat_tools import make_tools

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """你是 ReadAgent，一个专为长篇小说分析与理解而设计的智能助手。
你拥有以下工具来访问书籍的结构化知识库：

- search_knowledge：语义检索实体和章节摘要
- get_entity：精确查询某个实体（人物/地点/组织/物品/概念）的详细信息
- get_chapter_anchor：获取指定章节的摘要、关键事件、出场人物、伏笔和主题词
- get_timeline：获取章节范围内的事件时间线
- get_entity_relations：获取某个实体的所有关系
- search_chapters：搜索相关章节的原文片段
- edit_entity：修改实体信息（描述、别名、类型、属性）
- edit_anchor：修改章节锚点（摘要、关键事件、伏笔、主题词）

回答原则：
1. 优先调用工具获取准确信息，不依赖训练时的记忆
2. 当问题涉及具体细节时，主动使用多个工具进行多跳推理
3. 引用工具结果时，说明信息来源（如"根据第X章锚点"）
4. 对于编辑类请求，执行前先确认要修改的内容，执行后反馈修改结果
5. 使用中文回答，语气专业但友好"""


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
    tools = make_tools(book_id)
    agent = create_react_agent(llm, tools)

    lc_messages = [SystemMessage(content=_SYSTEM_PROMPT)]
    lc_messages.extend(_to_lc_messages(history))
    lc_messages.append(HumanMessage(content=user_message))

    full_content = ""
    tool_calls_log: list[dict[str, Any]] = []
    error_occurred = False

    try:
        async for event in agent.astream_events(
            {"messages": lc_messages},
            version="v1",
        ):
            kind: str = event.get("event", "")
            name: str = event.get("name", "")

            if kind == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                if chunk is None:
                    continue
                content = chunk.content
                # content 可能是 str 或 list（OpenAI 多模态格式）
                if isinstance(content, str) and content:
                    full_content += content
                    yield _sse("text", {"chunk": content})
                elif isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            text = item.get("text", "")
                            if text:
                                full_content += text
                                yield _sse("text", {"chunk": text})

            elif kind == "on_tool_start":
                raw_input = event["data"].get("input", {})
                # input 可能是 str（JSON）或 dict
                if isinstance(raw_input, str):
                    try:
                        parsed_input = json.loads(raw_input)
                    except json.JSONDecodeError:
                        parsed_input = {"raw": raw_input}
                else:
                    parsed_input = raw_input or {}

                tool_calls_log.append({"name": name, "input": parsed_input})
                yield _sse("tool_start", {"tool_name": name, "input": parsed_input})

            elif kind == "on_tool_end":
                raw_output = event["data"].get("output", "")
                output_str = (
                    str(raw_output) if not isinstance(raw_output, str) else raw_output
                )
                # 工具输出截断，避免前端消息过大
                yield _sse(
                    "tool_end",
                    {"tool_name": name, "output": output_str[:1000]},
                )

    except Exception as exc:
        logger.error("Chat Brain 运行时错误（book_id=%d）：%s", book_id, exc, exc_info=True)
        error_occurred = True
        yield _sse("error", {"message": f"对话处理出错：{exc}"})

    if not error_occurred:
        yield _sse("done", {"message": "完成"})

    # ── 持久化助手消息 ─────────────────────────────────────────────────────
    if full_content or tool_calls_log:
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
        except Exception as exc:
            logger.error("助手消息持久化失败（conv_id=%d）：%s", conversation_id, exc, exc_info=True)
