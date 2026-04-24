"""
Orchestrator Agent

调度 Entity Extractor 和 Anchor Builder 逐章处理书籍，
通过异步生成器产出 SSE 格式进度事件，支持前端实时展示进度。
"""

import asyncio
import json
import logging
from typing import AsyncGenerator

from sqlalchemy import select

from app.db.database import AsyncSessionLocal
from app.models.book import Book, ProcessingStatus
from app.models.chapter import Chapter
from app.agents.entity_extractor import extract_entities_for_chapter
from app.agents.anchor_builder import build_anchor_for_chapter

logger = logging.getLogger(__name__)


def _sse(event: str, data: dict) -> str:
    """格式化为 SSE 消息字符串。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def process_book_stream(book_id: int) -> AsyncGenerator[str, None]:
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

            # 已完成：直接返回完成事件
            if book.processing_status == ProcessingStatus.COMPLETED:
                yield _sse(
                    "complete",
                    {
                        "processed": book.processed_chapters,
                        "total": book.total_chapters or 0,
                        "failed_chapters": [],
                        "message": "已处理完成",
                    },
                )
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

            book.processing_status = ProcessingStatus.PROCESSING
            book.processed_chapters = 0
            await db.flush()

            total = len(chapters)
            yield _sse("start", {"total": total, "message": f"开始处理，共 {total} 章"})

            failed_chapters: list[int] = []

            for chapter in chapters:
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

                    book.processed_chapters += 1
                    await db.flush()

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
            await db.flush()

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
