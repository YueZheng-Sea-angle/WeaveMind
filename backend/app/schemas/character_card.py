from __future__ import annotations

from pydantic import BaseModel


# ── 子条目 ────────────────────────────────────────────────────────────────────

class CharacterCardEntryCreate(BaseModel):
    category: str
    title: str
    content: str | None = None
    enabled: bool = True
    sort_order: int = 0


class CharacterCardEntryUpdate(BaseModel):
    category: str | None = None
    title: str | None = None
    content: str | None = None
    enabled: bool | None = None
    sort_order: int | None = None


class CharacterCardEntryRead(BaseModel):
    id: int
    card_id: int
    category: str
    title: str
    content: str | None
    enabled: bool
    sort_order: int

    model_config = {"from_attributes": True}


# ── 角色卡 ────────────────────────────────────────────────────────────────────

class CharacterCardCreate(BaseModel):
    name: str
    entity_id: int | None = None
    summary: str | None = None
    enabled: bool = True


class CharacterCardUpdate(BaseModel):
    name: str | None = None
    entity_id: int | None = None
    summary: str | None = None
    enabled: bool | None = None


class CharacterCardRead(BaseModel):
    id: int
    book_id: int
    entity_id: int | None
    name: str
    summary: str | None
    enabled: bool
    entries: list[CharacterCardEntryRead] = []

    model_config = {"from_attributes": True}
