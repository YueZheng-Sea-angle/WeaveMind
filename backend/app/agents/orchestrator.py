"""
Orchestrator Agent

调度 Entity Extractor 和 Anchor Builder 逐章处理书籍，
通过异步生成器产出 SSE 格式进度事件，支持前端实时展示进度。
"""

import asyncio
import json
import logging
from typing import AsyncGenerator

from sqlalchemy import func, select

from app.db.database import AsyncSessionLocal
from app.models.book import Book, ProcessingStatus
from app.models.chapter import Chapter, ChapterAnchor
from app.agents.entity_extractor import extract_entities_for_chapter
from app.agents.anchor_builder import build_anchor_for_chapter
from app.agents.character_card_builder import update_character_cards_for_chapter

logger = logging.getLogger(__name__)


def _sse(event: str, data: dict) -> str:
    """格式化为 SSE 消息字符串。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _count_chapters_with_anchors(db, book_id: int) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(ChapterAnchor)
        .join(Chapter, Chapter.id == ChapterAnchor.chapter_id)
        .where(Chapter.book_id == book_id)
    )
    return int(result.scalar() or 0)


async def _finalize_if_already_analyzed(
    db, book: Book, chapters: list[Chapter], *, force: bool
) -> bool:
    """
    非强制模式下，若全书章节锚点已齐全，则修复状态并视为已完成，避免重复跑分析覆盖数据。
    返回 True 表示已处理完毕（调用方应直接结束流）。
    """
    if force or not chapters:
        return False

    anchored = await _count_chapters_with_anchors(db, book.id)
    if anchored < len(chapters):
        return False

    book.processing_status = ProcessingStatus.COMPLETED
    book.processed_chapters = len(chapters)
    book.total_chapters = len(chapters)
    await db.commit()
    return True


async def process_book_stream(
    book_id: int, *, force: bool = False
) -> AsyncGenerator[str, None]:
    """
    处理整本书的异步生成器，逐章运行 Entity Extractor + Anchor Builder。

    每章处理前后各推送一次 progress 事件，出错时推送 chapter_error 事件但继续处理后续章节。
    全部完成后推送 complete 事件，书籍状态更新为 COMPLETED 或 FAILED。

    SSE 事件类型：
        start          - 处理开始，携带总章节数
        progress       - 单章进度更新（status: "processing" | "done" | "error"）
        chapter_error  - 单章处理异常信息
        complete       - 全部完成
        error          - 致命错误（书籍不存在等）
    """
    async with AsyncSessionLocal() as db:
        try:
            book = await db.get(Book, book_id)
            if not book:
                yield _sse("error", {"message": "书籍不存在"})
                return

            chapters_result = await db.execute(
                select(Chapter)
                .where(Chapter.book_id == book_id)
                .order_by(Chapter.chapter_number)
            )
            chapters: list[Chapter] = list(chapters_result.scalars().all())

            if not chapters:
                yield _sse("error", {"message": "该书暂无章节，请先上传文件"})
                return

            total = len(chapters)

            # 非强制：已完成或数据已齐全（含卡在 processing 的脏状态）→ 不重复分析
            if not force and book.processing_status == ProcessingStatus.COMPLETED:
                yield _sse(
                    "complete",
                    {
                        "processed": book.processed_chapters or total,
                        "total": book.total_chapters or total,
                        "failed_chapters": [],
                        "message": "已处理完成",
                    },
                )
                return

            if await _finalize_if_already_analyzed(db, book, chapters, force=force):
                yield _sse(
                    "complete",
                    {
                        "processed": total,
                        "total": total,
                        "failed_chapters": [],
                        "message": "章节数据已存在，已跳过重复分析",
                    },
                )
                return

            # 非强制：从上次中断处续跑，不重置进度
            resume_from = 0
            if not force and book.processing_status == ProcessingStatus.PROCESSING:
                resume_from = min(book.processed_chapters or 0, total)
            elif force:
                book.processed_chapters = 0

            book.processing_status = ProcessingStatus.PROCESSING
            book.total_chapters = total
            await db.commit()

            if resume_from > 0:
                yield _sse(
                    "start",
                    {
                        "total": total,
                        "message": f"从第 {resume_from + 1} 章继续处理，共 {total} 章",
                    },
                )
            else:
                yield _sse("start", {"total": total, "message": f"开始处理，共 {total} 章"})

            failed_chapters: list[int] = []

            for chapter in chapters[resume_from:]:
                ch_num = chapter.chapter_number
                ch_title = chapter.title or f"第{ch_num}章"

                yield _sse(
                    "progress",
                    {
                        "chapter_number": ch_num,
                        "chapter_title": ch_title,
                        "status": "processing",
                        "processed": book.processed_chapters,
                        "total": total,
                    },
                )

                try:
                    await extract_entities_for_chapter(
                        chapter_id=chapter.id,
                        chapter_number=ch_num,
                        chapter_text=chapter.raw_text,
                        book_id=book_id,
                        db=db,
                    )
                    await build_anchor_for_chapter(
                        chapter_id=chapter.id,
                        chapter_number=ch_num,
                        chapter_text=chapter.raw_text,
                        book_id=book_id,
                        db=db,
                    )
                    await update_character_cards_for_chapter(
                        chapter_id=chapter.id,
                        chapter_number=ch_num,
                        chapter_text=chapter.raw_text,
                        book_id=book_id,
                        db=db,
                    )

                    book.processed_chapters += 1
                    await db.commit()

                    yield _sse(
                        "progress",
                        {
                            "chapter_number": ch_num,
                            "chapter_title": ch_title,
                            "status": "done",
                            "processed": book.processed_chapters,
                            "total": total,
                        },
                    )

                except Exception as exc:
                    failed_chapters.append(ch_num)
                    logger.error(
                        "章节 %d 处理失败：%s", ch_num, exc, exc_info=True
                    )
                    yield _sse(
                        "chapter_error",
                        {
                            "chapter_number": ch_num,
                            "chapter_title": ch_title,
                            "error": str(exc),
                        },
                    )

                # 给前端一点呼吸空间
                await asyncio.sleep(0)

            book.processing_status = (
                ProcessingStatus.COMPLETED
                if not failed_chapters
                else ProcessingStatus.FAILED
            )
            await db.commit()

            yield _sse(
                "complete",
                {
                    "processed": book.processed_chapters,
                    "total": total,
                    "failed_chapters": failed_chapters,
                    "message": (
                        "处理完成"
                        if not failed_chapters
                        else f"处理完成，{len(failed_chapters)} 章失败"
                    ),
                },
            )

        except Exception as exc:
            logger.error("书籍 %d 处理过程发生致命错误：%s", book_id, exc, exc_info=True)
            try:
                book = await db.get(Book, book_id)
                if book:
                    book.processing_status = ProcessingStatus.FAILED
                    await db.flush()
            except Exception:
                pass
            yield _sse("error", {"message": f"处理失败：{exc}"})
