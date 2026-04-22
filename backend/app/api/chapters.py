from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.database import get_db
from app.models.chapter import Chapter, ChapterAnchor
from app.schemas.chapter import ChapterRead, ChapterReadWithText, ChapterAnchorRead, ChapterAnchorUpdate

router = APIRouter()


@router.get("/{book_id}/chapters", response_model=list[ChapterRead])
async def list_chapters(book_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Chapter)
        .where(Chapter.book_id == book_id)
        .order_by(Chapter.chapter_number)
    )
    return result.scalars().all()


@router.get("/{book_id}/chapters/{chapter_id}", response_model=ChapterReadWithText)
async def get_chapter(book_id: int, chapter_id: int, db: AsyncSession = Depends(get_db)):
    chapter = await db.get(Chapter, chapter_id)
    if not chapter or chapter.book_id != book_id:
        raise HTTPException(status_code=404, detail="章节不存在")
    return chapter


@router.get("/{book_id}/chapters/{chapter_id}/anchor", response_model=ChapterAnchorRead)
async def get_chapter_anchor(book_id: int, chapter_id: int, db: AsyncSession = Depends(get_db)):
    chapter = await db.get(Chapter, chapter_id)
    if not chapter or chapter.book_id != book_id:
        raise HTTPException(status_code=404, detail="章节不存在")
    result = await db.execute(
        select(ChapterAnchor).where(ChapterAnchor.chapter_id == chapter_id)
    )
    anchor = result.scalar_one_or_none()
    if not anchor:
        raise HTTPException(status_code=404, detail="锚点尚未生成")
    return anchor


@router.patch("/{book_id}/chapters/{chapter_id}/anchor", response_model=ChapterAnchorRead)
async def update_chapter_anchor(
    book_id: int,
    chapter_id: int,
    payload: ChapterAnchorUpdate,
    db: AsyncSession = Depends(get_db),
):
    chapter = await db.get(Chapter, chapter_id)
    if not chapter or chapter.book_id != book_id:
        raise HTTPException(status_code=404, detail="章节不存在")
    result = await db.execute(
        select(ChapterAnchor).where(ChapterAnchor.chapter_id == chapter_id)
    )
    anchor = result.scalar_one_or_none()
    if not anchor:
        raise HTTPException(status_code=404, detail="锚点尚未生成")

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(anchor, field, value)

    await db.flush()
    await db.refresh(anchor)
    return anchor
