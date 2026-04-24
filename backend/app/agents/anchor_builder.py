"""
Anchor Builder Agent

逐章生成结构化章节锚点（摘要、关键事件、出场人物、伏笔、主题词），
写入 chapter_anchors 表并将摘要向量化后写入 ChromaDB。
"""

import asyncio
import logging

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.chapter import ChapterAnchor
from app.agents.base import get_processing_llm, get_embeddings
from app.db.chroma_client import get_or_create_collection, ChromaCollections

logger = logging.getLogger(__name__)

MAX_CHAPTER_CHARS = 8000


# ── LLM 结构化输出 Schema ────────────────────────────────────────────────────

class AnchorResult(BaseModel):
    summary: str = Field(
        description="章节摘要，200-400字，概括本章主要情节发展、关键转折和重要信息"
    )
    key_events: list[str] = Field(
        description="本章 3-8 个关键事件，每条为一句简洁描述"
    )
    characters_present: list[str] = Field(
        description="本章出场或被提及的人物名称列表（使用规范名称）"
    )
    foreshadowing: list[str] = Field(
        description="本章埋下的伏笔、悬念或铺垫，每条为一句描述；若无则返回空列表"
    )
    themes: list[str] = Field(
        description="本章核心主题词，3-5 个，如：成长、背叛、复仇、友情等"
    )


# ── 核心构建函数 ─────────────────────────────────────────────────────────────

async def build_anchor_for_chapter(
    chapter_id: int,
    chapter_number: int,
    chapter_text: str,
    book_id: int,
    db: AsyncSession,
) -> None:
    """
    为单章构建结构化锚点并写入数据库与向量库。

    - 使用 LLM structured output 生成锚点字段
    - 若该章锚点已存在则覆盖更新，否则新建
    - 章节摘要向量化后写入 ChromaDB anchor_summaries 集合
    """
    text = chapter_text[:MAX_CHAPTER_CHARS]

    llm = get_processing_llm()
    structured_llm = llm.with_structured_output(AnchorResult)

    messages = [
        (
            "system",
            (
                "你是一个专业的文学分析助手，负责为小说章节生成高质量的结构化锚点信息，"
                "用于构建可检索的知识库。\n"
                "要求：\n"
                "- summary：200-400字，要求信息密度高，能让读者快速了解本章核心内容\n"
                "- key_events：按时间顺序排列，每条一句话，突出因果关系\n"
                "- characters_present：使用人物最常用的称呼，不要重复\n"
                "- foreshadowing：仅列出文本中有明显暗示的伏笔，不过度解读\n"
                "- themes：精炼的关键词，3-5 个即可"
            ),
        ),
        (
            "human",
            f"请为以下小说章节（第 {chapter_number} 章）生成锚点信息：\n\n{text}",
        ),
    ]

    result: AnchorResult = await asyncio.to_thread(structured_llm.invoke, messages)

    # ── 写入或更新 chapter_anchors ────────────────────────────────────────────
    existing_result = await db.execute(
        select(ChapterAnchor).where(ChapterAnchor.chapter_id == chapter_id)
    )
    anchor = existing_result.scalar_one_or_none()

    if anchor:
        anchor.summary = result.summary
        anchor.key_events = result.key_events
        anchor.characters_present = result.characters_present
        anchor.foreshadowing = result.foreshadowing
        anchor.themes = result.themes
    else:
        anchor = ChapterAnchor(
            chapter_id=chapter_id,
            summary=result.summary,
            key_events=result.key_events,
            characters_present=result.characters_present,
            foreshadowing=result.foreshadowing,
            themes=result.themes,
        )
        db.add(anchor)

    await db.flush()
    await db.refresh(anchor)

    # ── ChromaDB 锚点摘要向量写入 ─────────────────────────────────────────────
    try:
        embed_model = get_embeddings()
        text_to_embed = f"第{chapter_number}章摘要：{result.summary}"
        vectors = await asyncio.to_thread(
            embed_model.embed_documents, [text_to_embed]
        )
        collection = await asyncio.to_thread(
            get_or_create_collection, ChromaCollections.ANCHORS
        )
        await asyncio.to_thread(
            collection.upsert,
            ids=[f"anchor_{anchor.id}"],
            embeddings=vectors,
            documents=[text_to_embed],
            metadatas=[
                {
                    "book_id": book_id,
                    "chapter_id": chapter_id,
                    "chapter_number": chapter_number,
                }
            ],
        )
    except Exception:
        logger.warning(
            "ChromaDB 锚点向量写入失败（章节 %d），继续处理",
            chapter_number,
            exc_info=True,
        )
