from datetime import datetime
from typing import Any
from pydantic import BaseModel


class ConversationCreate(BaseModel):
    title: str | None = None


class MessageRead(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str | None
    tool_calls: list[Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationRead(BaseModel):
    id: int
    book_id: int
    title: str | None
    created_at: datetime
    messages: list[MessageRead] = []

    model_config = {"from_attributes": True}


class ChatRequest(BaseModel):
    message: str
    model: str | None = None
    conversation_id: int | None = None
