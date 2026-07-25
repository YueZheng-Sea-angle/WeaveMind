from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.models.chapter import Chapter
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


# ── 自动构建：一键建立（全书 SSE）与按章构建 ──────────────────────────────────
# 说明：路由段数与 /{card_id} 系列不冲突，但仍置于前面以保持清晰。

@router.get("/{book_id}/character-cards/build/stream")
async def build_character_cards_stream_endpoint(book_id: int):
    """SSE 流：对全书逐章顺序构建/更新关键角色卡（「一键建立」）。

    仅运行角色卡 Agent，不重跑实体提取与锚点；适用于本功能上线前的旧书库。
    """
    from app.agents.character_card_builder import build_character_cards_stream

    return StreamingResponse(
        build_character_cards_stream(book_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/{book_id}/character-cards/build/chapter/{chapter_id}",
    response_model=list[CharacterCardRead],
)
async def build_character_cards_for_chapter_endpoint(
    book_id: int,
    chapter_id: int,
    db: AsyncSession = Depends(get_db),
):
    """仅针对单个章节调用角色卡 Agent（参考章节「重新分析」），构建/更新关键角色卡。

    返回该书最新的全部角色卡（含子条目）。
    """
    from app.agents.character_card_builder import update_character_cards_for_chapter

    chapter = await db.get(Chapter, chapter_id)
    if not chapter or chapter.book_id != book_id:
        raise HTTPException(status_code=404, detail="章节不存在")

    try:
        await update_character_cards_for_chapter(
            chapter_id=chapter.id,
            chapter_number=chapter.chapter_number,
            chapter_text=chapter.raw_text,
            book_id=book_id,
            db=db,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"角色卡构建失败：{exc}")

    result = await db.execute(
        select(CharacterCard)
        .where(CharacterCard.book_id == book_id)
        .options(selectinload(CharacterCard.entries))
        .order_by(CharacterCard.name)
    )
    return result.scalars().all()


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
