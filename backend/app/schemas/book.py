from datetime import datetime
from pydantic import BaseModel


class BookCreate(BaseModel):
    title: str
    author: str | None = None
    description: str | None = None


class BookUpdate(BaseModel):
    title: str | None = None
    author: str | None = None
    description: str | None = None


class BookListItem(BaseModel):
    id: int
    title: str
    author: str | None
    processing_status: str
    total_chapters: int
    processed_chapters: int
    created_at: datetime

    model_config = {"from_attributes": True}


class BookRead(BookListItem):
    description: str | None
    updated_at: datetime
