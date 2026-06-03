from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.models.character_card import (
    CharacterCard,
    CharacterCardEntry,
    VALID_CATEGORIES,
)
from app.schemas.character_card import (
    CharacterCardCreate,
    CharacterCardUpdate,
    CharacterCardRead,
    CharacterCardEntryCreate,
    CharacterCardEntryUpdate,
    CharacterCardEntryRead,
)

router = APIRouter()


async def _get_card_or_404(
    book_id: int, card_id: int, db: AsyncSession
) -> CharacterCard:
    result = await db.execute(
        select(CharacterCard)
        .where(CharacterCard.id == card_id)
        .options(selectinload(CharacterCard.entries))
    )
    card = result.scalar_one_or_none()
    if not card or card.book_id != book_id:
        raise HTTPException(status_code=404, detail="角色卡不存在")
    return card


# ── 角色卡 ────────────────────────────────────────────────────────────────────

@router.get("/{book_id}/character-cards", response_model=list[CharacterCardRead])
async def list_character_cards(
    book_id: int,
    q: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """列出本书所有角色卡（含全部子条目，包括已停用项，供用户管理启用状态）。"""
    stmt = (
        select(CharacterCard)
        .where(CharacterCard.book_id == book_id)
        .options(selectinload(CharacterCard.entries))
        .order_by(CharacterCard.name)
    )
    if q:
        stmt = stmt.where(CharacterCard.name.ilike(f"%{q}%"))
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post(
    "/{book_id}/character-cards", response_model=CharacterCardRead, status_code=201
)
async def create_character_card(
    book_id: int,
    payload: CharacterCardCreate,
    db: AsyncSession = Depends(get_db),
):
    card = CharacterCard(book_id=book_id, **payload.model_dump())
    db.add(card)
    await db.flush()
    return await _get_card_or_404(book_id, card.id, db)


@router.get(
    "/{book_id}/character-cards/{card_id}", response_model=CharacterCardRead
)
async def get_character_card(
    book_id: int, card_id: int, db: AsyncSession = Depends(get_db)
):
    return await _get_card_or_404(book_id, card_id, db)


@router.patch(
    "/{book_id}/character-cards/{card_id}", response_model=CharacterCardRead
)
async def update_character_card(
    book_id: int,
    card_id: int,
    payload: CharacterCardUpdate,
    db: AsyncSession = Depends(get_db),
):
    card = await _get_card_or_404(book_id, card_id, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(card, field, value)
    await db.flush()
    return await _get_card_or_404(book_id, card_id, db)


@router.delete("/{book_id}/character-cards/{card_id}", status_code=204)
async def delete_character_card(
    book_id: int, card_id: int, db: AsyncSession = Depends(get_db)
):
    card = await _get_card_or_404(book_id, card_id, db)
    await db.delete(card)


# ── 子条目 ────────────────────────────────────────────────────────────────────

@router.post(
    "/{book_id}/character-cards/{card_id}/entries",
    response_model=CharacterCardEntryRead,
    status_code=201,
)
async def create_card_entry(
    book_id: int,
    card_id: int,
    payload: CharacterCardEntryCreate,
    db: AsyncSession = Depends(get_db),
):
    await _get_card_or_404(book_id, card_id, db)
    if payload.category not in VALID_CATEGORIES:
        raise HTTPException(
            status_code=422,
            detail=f"无效的分类「{payload.category}」，可选：{', '.join(sorted(VALID_CATEGORIES))}",
        )
    entry = CharacterCardEntry(card_id=card_id, **payload.model_dump())
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return entry


@router.patch(
    "/{book_id}/character-cards/{card_id}/entries/{entry_id}",
    response_model=CharacterCardEntryRead,
)
async def update_card_entry(
    book_id: int,
    card_id: int,
    entry_id: int,
    payload: CharacterCardEntryUpdate,
    db: AsyncSession = Depends(get_db),
):
    await _get_card_or_404(book_id, card_id, db)
    entry = await db.get(CharacterCardEntry, entry_id)
    if not entry or entry.card_id != card_id:
        raise HTTPException(status_code=404, detail="条目不存在")

    data = payload.model_dump(exclude_unset=True)
    if "category" in data and data["category"] not in VALID_CATEGORIES:
        raise HTTPException(
            status_code=422,
            detail=f"无效的分类「{data['category']}」，可选：{', '.join(sorted(VALID_CATEGORIES))}",
        )
    for field, value in data.items():
        setattr(entry, field, value)
    await db.flush()
    await db.refresh(entry)
    return entry


@router.delete(
    "/{book_id}/character-cards/{card_id}/entries/{entry_id}", status_code=204
)
async def delete_card_entry(
    book_id: int,
    card_id: int,
    entry_id: int,
    db: AsyncSession = Depends(get_db),
):
    await _get_card_or_404(book_id, card_id, db)
    entry = await db.get(CharacterCardEntry, entry_id)
    if not entry or entry.card_id != card_id:
        raise HTTPException(status_code=404, detail="条目不存在")
    await db.delete(entry)
