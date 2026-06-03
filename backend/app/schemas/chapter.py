from __future__ import annotations

from typing import Any
from pydantic import BaseModel


class ChapterRead(BaseModel):
    id: int
    book_id: int
    chapter_number: int
    title: str | None
    word_count: int

    model_config = {"from_attributes": True}


class ChapterReadWithText(ChapterRead):
    raw_text: str


class ChapterAnchorRead(BaseModel):
    id: int
    chapter_id: int
    summary: str | None
    key_events: list[Any]
    characters_present: list[Any]
    foreshadowing: list[Any]
    themes: list[Any]

    model_config = {"from_attributes": True}


class ChapterAnchorUpdate(BaseModel):
    summary: str | None = None
    key_events: list[Any] | None = None
    characters_present: list[Any] | None = None
    foreshadowing: list[Any] | None = None
    themes: list[Any] | None = None


class ChapterCreate(BaseModel):
    title: str | None = None
    raw_text: str
    # 期望插入的章节序号；为空则追加到末尾。若与现有章节冲突，则其后章节顺延
    chapter_number: int | None = None


class ChapterUpdate(BaseModel):
    title: str | None = None
    raw_text: str | None = None
