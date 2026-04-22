from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.models.conversation import Conversation
from app.schemas.conversation import ConversationCreate, ConversationRead

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
