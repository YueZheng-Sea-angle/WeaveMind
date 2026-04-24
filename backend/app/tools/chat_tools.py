"""
Chat Brain 工具集

工厂函数 make_tools(book_id) 返回绑定到指定书籍的 LangChain 工具列表。
每个工具内部创建独立的 AsyncSession，不依赖外部传入的数据库会话。
"""

import asyncio
import json
import logging
from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from app.db.chroma_client import ChromaCollections, get_or_create_collection
from app.db.database import AsyncSessionLocal
from app.models.chapter import Chapter, ChapterAnchor
from app.models.entity import Entity, Relation

logger = logging.getLogger(__name__)

_MAX_TEXT_SNIPPET = 600
_MAX_TOOL_OUTPUT = 2000


def _truncate(text: str, limit: int = _MAX_TOOL_OUTPUT) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n…（已截断，共 {len(text)} 字）"


# ── Pydantic 输入 Schema（用于结构化工具调用） ─────────────────────────────


class EditEntityInput(BaseModel):
    entity_name: str = Field(description="要修改的实体规范名称")
    description: str | None = Field(None, description="新的描述文本；None 表示不修改")
    aliases: list[str] | None = Field(None, description="新的别名列表；None 表示不修改")
    entity_type: str | None = Field(
        None,
        description="新的实体类型：character / organization / location / object / concept；None 表示不修改",
    )
    attributes_json: str | None = Field(
        None,
        description='要合并到 attributes 的键值对，JSON 字符串格式，如 {"age": 30}；None 表示不修改',
    )


class EditAnchorInput(BaseModel):
    chapter_number: int = Field(description="要修改锚点的章节序号（从 1 开始）")
    summary: str | None = Field(None, description="新的章节摘要；None 表示不修改")
    key_events: list[str] | None = Field(None, description="新的关键事件列表；None 表示不修改")
    foreshadowing: list[str] | None = Field(None, description="新的伏笔列表；None 表示不修改")
    themes: list[str] | None = Field(None, description="新的主题词列表；None 表示不修改")


# ── 工具工厂 ──────────────────────────────────────────────────────────────────


def make_tools(book_id: int) -> list:
    """
    创建绑定到指定书籍的工具列表。

    所有工具内部独立管理数据库会话，可安全在 LangGraph ReAct Agent 中并发调用。
    """

    # ── 1. search_knowledge ──────────────────────────────────────────────────

    @tool
    async def search_knowledge(query: str) -> str:
        """语义检索书籍知识库，同时搜索实体描述和章节锚点摘要，返回最相关的内容片段。
        适用于宽泛问题、跨章节综合检索、主题探索等场景。"""
        from app.agents.base import get_embeddings

        embed_model = get_embeddings()
        try:
            query_vec = await asyncio.to_thread(embed_model.embed_query, query)
        except Exception as exc:
            return f"向量检索失败：{exc}"

        parts: list[str] = []

        # 搜索实体集合
        try:
            col = await asyncio.to_thread(get_or_create_collection, ChromaCollections.ENTITIES)
            res = await asyncio.to_thread(
                col.query,
                query_embeddings=[query_vec],
                n_results=5,
                where={"book_id": book_id},
            )
            docs = res.get("documents", [[]])[0]
            if docs:
                parts.append("【相关实体】")
                for doc in docs:
                    parts.append(f"  • {doc[:200]}")
        except Exception as exc:
            logger.warning("实体向量检索失败: %s", exc)

        # 搜索章节锚点集合
        try:
            col = await asyncio.to_thread(get_or_create_collection, ChromaCollections.ANCHORS)
            res = await asyncio.to_thread(
                col.query,
                query_embeddings=[query_vec],
                n_results=5,
                where={"book_id": book_id},
            )
            docs = res.get("documents", [[]])[0]
            metas = res.get("metadatas", [[]])[0]
            if docs:
                parts.append("【相关章节摘要】")
                for doc, meta in zip(docs, metas):
                    ch = meta.get("chapter_number", "?")
                    parts.append(f"  • 第{ch}章：{doc[:300]}")
        except Exception as exc:
            logger.warning("锚点向量检索失败: %s", exc)

        return _truncate("\n".join(parts)) if parts else "知识库中未找到与该查询相关的内容。"

    # ── 2. get_entity ────────────────────────────────────────────────────────

    @tool
    async def get_entity(name: str) -> str:
        """精确查询实体详细信息（人物、地点、组织、物品、概念）。
        支持别名模糊匹配，返回实体的描述、属性、别名、首次出场章节等完整信息。"""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Entity).where(Entity.book_id == book_id)
            )
            entities: list[Entity] = list(result.scalars().all())

        name_lower = name.strip().lower()
        matched: Entity | None = None
        for ent in entities:
            if ent.name.lower() == name_lower:
                matched = ent
                break
            for alias in (ent.aliases or []):
                if alias.lower() == name_lower:
                    matched = ent
                    break
            if matched:
                break

        # 模糊包含匹配
        if not matched:
            for ent in entities:
                if name_lower in ent.name.lower() or ent.name.lower() in name_lower:
                    matched = ent
                    break

        if not matched:
            return f"未找到名为「{name}」的实体，请检查名称是否正确，或尝试使用 search_knowledge 进行语义检索。"

        aliases_str = "、".join(matched.aliases or []) or "无"
        attrs_str = json.dumps(matched.attributes or {}, ensure_ascii=False)
        return (
            f"【实体：{matched.name}】\n"
            f"类型：{matched.type}\n"
            f"别名：{aliases_str}\n"
            f"首次出场：第{matched.first_appearance_chapter}章\n"
            f"描述：{matched.description or '暂无描述'}\n"
            f"属性：{attrs_str}"
        )

    # ── 3. get_chapter_anchor ────────────────────────────────────────────────

    @tool
    async def get_chapter_anchor(chapter_number: int) -> str:
        """获取指定章节的结构化锚点信息，包含章节摘要、关键事件列表、出场人物、伏笔线索和主题词。
        适用于了解特定章节内容、追踪章节脉络等场景。"""
        async with AsyncSessionLocal() as db:
            ch_result = await db.execute(
                select(Chapter).where(
                    Chapter.book_id == book_id,
                    Chapter.chapter_number == chapter_number,
                )
            )
            chapter = ch_result.scalar_one_or_none()
            if not chapter:
                return f"未找到第{chapter_number}章，请确认章节序号是否正确。"

            anchor_result = await db.execute(
                select(ChapterAnchor).where(ChapterAnchor.chapter_id == chapter.id)
            )
            anchor = anchor_result.scalar_one_or_none()

        if not anchor:
            return f"第{chapter_number}章（{chapter.title or '无标题'}）尚未生成锚点信息，请先完成书籍处理。"

        events_str = "\n".join(f"  {i+1}. {e}" for i, e in enumerate(anchor.key_events or []))
        chars_str = "、".join(anchor.characters_present or []) or "无"
        fore_str = "\n".join(f"  • {f}" for f in anchor.foreshadowing or []) or "  无"
        themes_str = "、".join(anchor.themes or []) or "无"

        return (
            f"【第{chapter_number}章锚点：{chapter.title or '无标题'}】\n\n"
            f"摘要：\n{anchor.summary or '暂无摘要'}\n\n"
            f"关键事件：\n{events_str or '  无'}\n\n"
            f"出场人物：{chars_str}\n\n"
            f"伏笔线索：\n{fore_str}\n\n"
            f"主题词：{themes_str}"
        )

    # ── 4. get_timeline ──────────────────────────────────────────────────────

    @tool
    async def get_timeline(start_chapter: int, end_chapter: int) -> str:
        """获取指定章节范围内的事件时间线，按章节顺序列出各章关键事件。
        适用于梳理故事发展脉络、了解情节走向等场景。"""
        if end_chapter < start_chapter:
            start_chapter, end_chapter = end_chapter, start_chapter
        end_chapter = min(end_chapter, start_chapter + 29)  # 最多 30 章，避免输出过长

        async with AsyncSessionLocal() as db:
            ch_result = await db.execute(
                select(Chapter)
                .where(
                    Chapter.book_id == book_id,
                    Chapter.chapter_number >= start_chapter,
                    Chapter.chapter_number <= end_chapter,
                )
                .order_by(Chapter.chapter_number)
            )
            chapters = list(ch_result.scalars().all())

            if not chapters:
                return f"未找到第{start_chapter}章到第{end_chapter}章的内容。"

            chapter_ids = [c.id for c in chapters]
            anchor_result = await db.execute(
                select(ChapterAnchor).where(ChapterAnchor.chapter_id.in_(chapter_ids))
            )
            anchors = {a.chapter_id: a for a in anchor_result.scalars().all()}

        lines: list[str] = [f"【时间线：第{start_chapter}章 → 第{end_chapter}章】\n"]
        for ch in chapters:
            anchor = anchors.get(ch.id)
            lines.append(f"── 第{ch.chapter_number}章 {ch.title or ''} ──")
            if anchor and anchor.key_events:
                for i, evt in enumerate(anchor.key_events, 1):
                    lines.append(f"  {i}. {evt}")
            else:
                lines.append("  （暂无锚点信息）")
            lines.append("")

        return _truncate("\n".join(lines))

    # ── 5. get_entity_relations ──────────────────────────────────────────────

    @tool
    async def get_entity_relations(entity_name: str) -> str:
        """获取指定实体与其他实体的所有关系，返回关系类型、描述及涉及的章节范围。
        适用于了解角色关系网络、梳理人物纠葛等场景。"""
        async with AsyncSessionLocal() as db:
            # 先找实体
            ent_result = await db.execute(
                select(Entity).where(Entity.book_id == book_id)
            )
            entities = list(ent_result.scalars().all())

        name_lower = entity_name.strip().lower()
        matched: Entity | None = None
        for ent in entities:
            if ent.name.lower() == name_lower:
                matched = ent
                break
            for alias in (ent.aliases or []):
                if alias.lower() == name_lower:
                    matched = ent
                    break
            if matched:
                break
        if not matched:
            for ent in entities:
                if name_lower in ent.name.lower():
                    matched = ent
                    break

        if not matched:
            return f"未找到实体「{entity_name}」，请检查名称或使用 search_knowledge 查找。"

        async with AsyncSessionLocal() as db:
            rel_result = await db.execute(
                select(Relation).where(
                    Relation.book_id == book_id,
                    or_(Relation.source_id == matched.id, Relation.target_id == matched.id),
                )
            )
            relations = list(rel_result.scalars().all())

            entity_ids = set()
            for r in relations:
                entity_ids.add(r.source_id)
                entity_ids.add(r.target_id)
            entity_ids.discard(matched.id)

            related_result = await db.execute(
                select(Entity).where(Entity.id.in_(entity_ids))
            )
            entity_map: dict[int, Entity] = {e.id: e for e in related_result.scalars().all()}

        if not relations:
            return f"「{matched.name}」暂无已记录的关系。"

        lines = [f"【{matched.name} 的关系网络】（共 {len(relations)} 条）\n"]
        for rel in relations:
            if rel.source_id == matched.id:
                other = entity_map.get(rel.target_id)
                direction = f"{matched.name} → {other.name if other else '?'}"
            else:
                other = entity_map.get(rel.source_id)
                direction = f"{other.name if other else '?'} → {matched.name}"

            ch_range = (
                f"第{'、'.join(str(c) for c in rel.chapter_range[:5])}章"
                if rel.chapter_range
                else "章节不详"
            )
            lines.append(
                f"  [{rel.relation_type}] {direction}\n"
                f"    描述：{rel.description or '无'}\n"
                f"    出现：{ch_range}"
            )

        return _truncate("\n".join(lines))

    # ── 6. search_chapters ───────────────────────────────────────────────────

    @tool
    async def search_chapters(query: str) -> str:
        """搜索与查询最相关的章节原文片段，先通过语义检索定位章节，再返回原文内容摘录。
        适用于查找特定情节出处、寻找原文依据等场景。"""
        from app.agents.base import get_embeddings

        embed_model = get_embeddings()
        try:
            query_vec = await asyncio.to_thread(embed_model.embed_query, query)
            col = await asyncio.to_thread(get_or_create_collection, ChromaCollections.ANCHORS)
            res = await asyncio.to_thread(
                col.query,
                query_embeddings=[query_vec],
                n_results=3,
                where={"book_id": book_id},
            )
            metas = res.get("metadatas", [[]])[0]
            chapter_ids = [m.get("chapter_id") for m in metas if m.get("chapter_id")]
        except Exception as exc:
            logger.warning("向量检索失败，退回关键字搜索: %s", exc)
            chapter_ids = []

        if not chapter_ids:
            return "未能定位到相关章节，请尝试使用 search_knowledge 进行综合检索。"

        async with AsyncSessionLocal() as db:
            ch_result = await db.execute(
                select(Chapter).where(Chapter.id.in_(chapter_ids))
            )
            chapters_map = {c.id: c for c in ch_result.scalars().all()}

        parts: list[str] = [f"【与「{query}」相关的章节原文片段】\n"]
        for cid in chapter_ids:
            ch = chapters_map.get(cid)
            if not ch:
                continue
            snippet = ch.raw_text[:_MAX_TEXT_SNIPPET].replace("\n", " ").strip()
            parts.append(
                f"── 第{ch.chapter_number}章 {ch.title or ''} ──\n{snippet}…\n"
            )

        return _truncate("\n".join(parts))

    # ── 7. edit_entity ───────────────────────────────────────────────────────

    @tool(args_schema=EditEntityInput)
    async def edit_entity(
        entity_name: str,
        description: str | None = None,
        aliases: list[str] | None = None,
        entity_type: str | None = None,
        attributes_json: str | None = None,
    ) -> str:
        """修改书籍中某个实体的信息，支持修改描述、别名列表、实体类型和属性。
        修改后会同步更新向量库，使后续语义检索反映最新内容。"""
        from app.agents.base import get_embeddings

        async with AsyncSessionLocal() as db:
            ent_result = await db.execute(
                select(Entity).where(Entity.book_id == book_id)
            )
            entities = list(ent_result.scalars().all())

        name_lower = entity_name.strip().lower()
        matched: Entity | None = None
        for ent in entities:
            if ent.name.lower() == name_lower:
                matched = ent
                break
            for alias in (ent.aliases or []):
                if alias.lower() == name_lower:
                    matched = ent
                    break
            if matched:
                break

        if not matched:
            return f"未找到实体「{entity_name}」，无法修改。"

        changed: list[str] = []
        async with AsyncSessionLocal() as db:
            ent = await db.get(Entity, matched.id)
            if ent is None:
                return "数据库查询失败，请重试。"

            if description is not None:
                ent.description = description
                changed.append("描述")
            if aliases is not None:
                ent.aliases = aliases
                changed.append("别名")
            if entity_type is not None:
                valid = {"character", "organization", "location", "object", "concept"}
                if entity_type not in valid:
                    return f"无效的实体类型「{entity_type}」，请使用：{', '.join(valid)}"
                ent.type = entity_type
                changed.append("类型")
            if attributes_json is not None:
                try:
                    patch = json.loads(attributes_json)
                    current = dict(ent.attributes or {})
                    current.update(patch)
                    ent.attributes = current
                    changed.append("属性")
                except json.JSONDecodeError:
                    return f"attributes_json 格式错误，请传入合法 JSON 字符串。"

            if not changed:
                return "未提供任何修改内容，实体信息未变更。"

            await db.commit()
            await db.refresh(ent)

            # 同步更新 ChromaDB
            try:
                embed_model = get_embeddings()
                text = f"{ent.name}（{ent.type}）：{ent.description or '暂无描述'}"
                vec = await asyncio.to_thread(embed_model.embed_documents, [text])
                col = await asyncio.to_thread(get_or_create_collection, ChromaCollections.ENTITIES)
                await asyncio.to_thread(
                    col.upsert,
                    ids=[f"entity_{ent.id}"],
                    embeddings=vec,
                    documents=[text],
                    metadatas=[{
                        "book_id": book_id,
                        "entity_id": ent.id,
                        "entity_type": ent.type,
                        "entity_name": ent.name,
                    }],
                )
            except Exception as exc:
                logger.warning("实体向量更新失败: %s", exc)

        return f"已成功修改「{matched.name}」的：{', '.join(changed)}。"

    # ── 8. edit_anchor ───────────────────────────────────────────────────────

    @tool(args_schema=EditAnchorInput)
    async def edit_anchor(
        chapter_number: int,
        summary: str | None = None,
        key_events: list[str] | None = None,
        foreshadowing: list[str] | None = None,
        themes: list[str] | None = None,
    ) -> str:
        """修改指定章节的锚点信息，支持修改摘要、关键事件、伏笔线索和主题词。
        修改后会同步更新向量库，使后续语义检索反映最新内容。"""
        from app.agents.base import get_embeddings

        async with AsyncSessionLocal() as db:
            ch_result = await db.execute(
                select(Chapter).where(
                    Chapter.book_id == book_id,
                    Chapter.chapter_number == chapter_number,
                )
            )
            chapter = ch_result.scalar_one_or_none()
            if not chapter:
                return f"未找到第{chapter_number}章。"

            anchor_result = await db.execute(
                select(ChapterAnchor).where(ChapterAnchor.chapter_id == chapter.id)
            )
            anchor = anchor_result.scalar_one_or_none()
            if not anchor:
                return f"第{chapter_number}章尚未生成锚点，请先完成书籍处理。"

            changed: list[str] = []
            if summary is not None:
                anchor.summary = summary
                changed.append("摘要")
            if key_events is not None:
                anchor.key_events = key_events
                changed.append("关键事件")
            if foreshadowing is not None:
                anchor.foreshadowing = foreshadowing
                changed.append("伏笔线索")
            if themes is not None:
                anchor.themes = themes
                changed.append("主题词")

            if not changed:
                return "未提供任何修改内容，锚点未变更。"

            await db.commit()
            await db.refresh(anchor)

            # 同步更新 ChromaDB
            try:
                embed_model = get_embeddings()
                text = f"第{chapter_number}章摘要：{anchor.summary or ''}"
                vec = await asyncio.to_thread(embed_model.embed_documents, [text])
                col = await asyncio.to_thread(get_or_create_collection, ChromaCollections.ANCHORS)
                await asyncio.to_thread(
                    col.upsert,
                    ids=[f"anchor_{anchor.id}"],
                    embeddings=vec,
                    documents=[text],
                    metadatas=[{
                        "book_id": book_id,
                        "chapter_id": chapter.id,
                        "chapter_number": chapter_number,
                    }],
                )
            except Exception as exc:
                logger.warning("锚点向量更新失败: %s", exc)

        return f"已成功修改第{chapter_number}章锚点的：{', '.join(changed)}。"

    return [
        search_knowledge,
        get_entity,
        get_chapter_anchor,
        get_timeline,
        get_entity_relations,
        search_chapters,
        edit_entity,
        edit_anchor,
    ]
