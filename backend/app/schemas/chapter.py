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
