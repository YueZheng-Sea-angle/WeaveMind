from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.models.conversation import Conversation, Message
from app.schemas.conversation import ChatRequest, ConversationCreate, ConversationRead

router = APIRouter()


@router.get("/{book_id}/conversations", response_model=list[ConversationRead])
async def list_conversations(book_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Conversation)
        .where(Conversation.book_id == book_id)
        .options(selectinload(Conversation.messages))
        .order_by(Conversation.created_at.desc())
    )
    return result.scalars().all()


@router.post("/{book_id}/conversations", response_model=ConversationRead, status_code=201)
async def create_conversation(
    book_id: int, payload: ConversationCreate, db: AsyncSession = Depends(get_db)
):
    conv = Conversation(book_id=book_id, **payload.model_dump())
    db.add(conv)
    await db.flush()
    result = await db.execute(
        select(Conversation)
        .where(Conversation.id == conv.id)
        .options(selectinload(Conversation.messages))
    )
    return result.scalar_one()


@router.get("/{book_id}/conversations/{conv_id}", response_model=ConversationRead)
async def get_conversation(book_id: int, conv_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Conversation)
        .where(Conversation.id == conv_id, Conversation.book_id == book_id)
        .options(selectinload(Conversation.messages))
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")
    return conv


@router.delete("/{book_id}/conversations/{conv_id}", status_code=204)
async def delete_conversation(book_id: int, conv_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Conversation).where(Conversation.id == conv_id, Conversation.book_id == book_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")
    await db.delete(conv)


@router.post("/{book_id}/conversations/{conv_id}/chat")
async def chat_message(
    book_id: int,
    conv_id: int,
    payload: ChatRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    SSE 流式聊天端点。

    接收用户消息，加载历史记录，启动 Chat Brain Agent，以 SSE 格式流式推送：
      - text       —— LLM 文本片段
      - tool_start —— 工具调用开始（含工具名与输入参数）
      - tool_end   —— 工具调用结束（含输出摘要）
      - done       —— 完成信号
      - error      —— 错误信息
    """
    # 验证对话存在且归属正确
    conv_result = await db.execute(
        select(Conversation)
        .where(Conversation.id == conv_id, Conversation.book_id == book_id)
        .options(selectinload(Conversation.messages))
    )
    conv = conv_result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")

    # 持久化用户消息
    user_msg = Message(
        conversation_id=conv_id,
        role="user",
        content=payload.message,
        tool_calls=[],
    )
    db.add(user_msg)
    await db.commit()

    # 构造历史消息列表（user_msg 已提交，不需再传入 chat_stream）
    history = [
        {"role": m.role, "content": m.content}
        for m in conv.messages
        if m.id != user_msg.id  # 排除刚写入的用户消息，由 chat_stream 单独处理
    ]

    from app.agents.chat_brain import chat_stream

    return StreamingResponse(
        chat_stream(
            book_id=book_id,
            conversation_id=conv_id,
            history=history,
            user_message=payload.message,
            model=payload.model,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
