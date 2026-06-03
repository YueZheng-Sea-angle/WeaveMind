import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.database import get_db
from app.models.book import Book
from app.models.chapter import Chapter, ChapterAnchor
from app.schemas.chapter import (
    ChapterRead,
    ChapterReadWithText,
    ChapterAnchorRead,
    ChapterAnchorUpdate,
    ChapterCreate,
    ChapterUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{book_id}/chapters", response_model=list[ChapterRead])
async def list_chapters(book_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Chapter)
        .where(Chapter.book_id == book_id)
        .order_by(Chapter.chapter_number)
    )
    return result.scalars().all()


@router.post("/{book_id}/chapters", response_model=ChapterReadWithText, status_code=201)
async def create_chapter(
    book_id: int,
    payload: ChapterCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    向已有书籍新增一个章节。

    - chapter_number 为空：追加到末尾
    - chapter_number 指定且与现有章节冲突：从该位置插入，其后章节序号顺延 +1
    新章节不会自动生成锚点，可在章节页点击「重新分析」生成。
    """
    book = await db.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="书籍不存在")

    result = await db.execute(
        select(Chapter)
        .where(Chapter.book_id == book_id)
        .order_by(Chapter.chapter_number)
    )
    chapters: list[Chapter] = list(result.scalars().all())
    max_num = chapters[-1].chapter_number if chapters else 0

    if payload.chapter_number is None or payload.chapter_number > max_num:
        new_num = max_num + 1
    else:
        new_num = max(1, payload.chapter_number)
        for ch in chapters:
            if ch.chapter_number >= new_num:
                ch.chapter_number += 1

    text = payload.raw_text or ""
    chapter = Chapter(
        book_id=book_id,
        chapter_number=new_num,
        title=payload.title,
        raw_text=text,
        word_count=len(text),
    )
    db.add(chapter)
    book.total_chapters = (book.total_chapters or 0) + 1

    await db.flush()
    await db.refresh(chapter)
    return chapter


@router.patch("/{book_id}/chapters/{chapter_id}", response_model=ChapterReadWithText)
async def update_chapter(
    book_id: int,
    chapter_id: int,
    payload: ChapterUpdate,
    db: AsyncSession = Depends(get_db),
):
    """编辑章节标题或正文。修改正文后可在章节页点击「重新分析」更新锚点。"""
    chapter = await db.get(Chapter, chapter_id)
    if not chapter or chapter.book_id != book_id:
        raise HTTPException(status_code=404, detail="章节不存在")

    data = payload.model_dump(exclude_unset=True)
    if "title" in data:
        chapter.title = data["title"]
    if "raw_text" in data and data["raw_text"] is not None:
        chapter.raw_text = data["raw_text"]
        chapter.word_count = len(data["raw_text"])

    await db.flush()
    await db.refresh(chapter)
    return chapter


@router.delete("/{book_id}/chapters/{chapter_id}", status_code=204)
async def delete_chapter(
    book_id: int,
    chapter_id: int,
    db: AsyncSession = Depends(get_db),
):
    """删除章节，其后章节序号自动前移，书籍章节总数相应减一。"""
    chapter = await db.get(Chapter, chapter_id)
    if not chapter or chapter.book_id != book_id:
        raise HTTPException(status_code=404, detail="章节不存在")

    removed_num = chapter.chapter_number
    await db.delete(chapter)
    await db.flush()

    result = await db.execute(
        select(Chapter)
        .where(Chapter.book_id == book_id, Chapter.chapter_number > removed_num)
    )
    for ch in result.scalars().all():
        ch.chapter_number -= 1

    book = await db.get(Book, book_id)
    if book:
        book.total_chapters = max(0, (book.total_chapters or 1) - 1)

    await db.flush()


@router.get("/{book_id}/chapters/{chapter_id}", response_model=ChapterReadWithText)
async def get_chapter(book_id: int, chapter_id: int, db: AsyncSession = Depends(get_db)):
    chapter = await db.get(Chapter, chapter_id)
    if not chapter or chapter.book_id != book_id:
        raise HTTPException(status_code=404, detail="章节不存在")
    return chapter


@router.post("/{book_id}/chapters/{chapter_id}/reprocess", response_model=ChapterAnchorRead)
async def reprocess_chapter(book_id: int, chapter_id: int, db: AsyncSession = Depends(get_db)):
    """
    重新分析单个章节：重跑实体提取 + 锚点构建（覆盖更新该章锚点）。

    适用场景：
    - 整书处理时该章分析失败，想单独补跑而不必重传整本书
    - 用户改动了章节原文后，想据新内容重新生成锚点与实体
    """
    from app.agents.entity_extractor import extract_entities_for_chapter
    from app.agents.anchor_builder import build_anchor_for_chapter

    chapter = await db.get(Chapter, chapter_id)
    if not chapter or chapter.book_id != book_id:
        raise HTTPException(status_code=404, detail="章节不存在")

    try:
        await extract_entities_for_chapter(
            chapter_id=chapter.id,
            chapter_number=chapter.chapter_number,
            chapter_text=chapter.raw_text,
            book_id=book_id,
            db=db,
        )
        await build_anchor_for_chapter(
            chapter_id=chapter.id,
            chapter_number=chapter.chapter_number,
            chapter_text=chapter.raw_text,
            book_id=book_id,
            db=db,
        )
    except Exception as exc:
        logger.error(
            "章节 %d 重新分析失败：%s", chapter.chapter_number, exc, exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"重新分析失败：{exc}")

    result = await db.execute(
        select(ChapterAnchor).where(ChapterAnchor.chapter_id == chapter_id)
    )
    anchor = result.scalar_one_or_none()
    if not anchor:
        raise HTTPException(status_code=500, detail="锚点生成失败")
    return anchor


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
