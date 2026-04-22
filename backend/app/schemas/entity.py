from typing import Any
from pydantic import BaseModel


class EntityCreate(BaseModel):
    name: str
    aliases: list[str] = []
    type: str = "character"
    description: str | None = None
    attributes: dict[str, Any] = {}
    first_appearance_chapter: int | None = None


class EntityUpdate(BaseModel):
    name: str | None = None
    aliases: list[str] | None = None
    type: str | None = None
    description: str | None = None
    attributes: dict[str, Any] | None = None


class EntityRead(EntityCreate):
    id: int
    book_id: int

    model_config = {"from_attributes": True}


class RelationRead(BaseModel):
    id: int
    book_id: int
    source_id: int
    target_id: int
    relation_type: str
    description: str | None
    chapter_range: list[int]

    model_config = {"from_attributes": True}


class EventRead(BaseModel):
    id: int
    book_id: int
    chapter_id: int | None
    name: str
    description: str | None
    involved_entities: list[Any]
    story_timestamp: str | None

    model_config = {"from_attributes": True}
