"""
Chat Brain 工具集

工厂函数 make_tools(book_id) 返回绑定到指定书籍的 LangChain 工具列表。
每个工具内部创建独立的 AsyncSession，不依赖外部传入的数据库会话。
"""

from __future__ import annotations

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
_MAX_CHAPTER_TEXT = 8000  # get_chapter_text 全文返回上限，超出建议改用 get_chapter_lines
_MAX_LINE_SPAN = 200  # get_chapter_lines 单次最多返回的行数


def _truncate(text: str, limit: int = _MAX_TOOL_OUTPUT) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n…（已截断，共 {len(text)} 字）"


# ── Pydantic 输入 Schema（用于结构化工具调用） ─────────────────────────────


class CreateEntityInput(BaseModel):
    name: str = Field(description="新实体的规范名称（人物用全名或最常用称呼）")
    entity_type: str = Field(
        description="实体类型，必须是以下之一：character / organization / location / object / concept",
    )
    description: str | None = Field(None, description="实体的简短描述（1-3 句话）")
    aliases: list[str] | None = Field(None, description="别名、绰号、简称列表")
    attributes_json: str | None = Field(
        None,
        description='额外属性，JSON 字符串格式，如 {"gender": "女", "age": 18}',
    )
    first_appearance_chapter: int | None = Field(
        None, description="首次出场章节序号（从 1 开始）；未知可留空"
    )


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


class DeleteEntityInput(BaseModel):
    entity_name: str = Field(description="要删除的实体规范名称或别名")


class EditAnchorInput(BaseModel):
    chapter_number: int = Field(description="要修改锚点的章节序号（从 1 开始）")
    summary: str | None = Field(None, description="新的章节摘要；None 表示不修改")
    key_events: list[str] | None = Field(None, description="新的关键事件列表；None 表示不修改")
    foreshadowing: list[str] | None = Field(None, description="新的伏笔列表；None 表示不修改")
    themes: list[str] | None = Field(None, description="新的主题词列表；None 表示不修改")


class CreateRelationInput(BaseModel):
    source_name: str = Field(description="关系起点实体的名称或别名（方向：起点 → 终点）")
    target_name: str = Field(description="关系终点实体的名称或别名")
    relation_type: str = Field(
        description="关系类型，简短词组，如：亲属、朋友、敌对、师徒、隶属、爱慕 等",
    )
    description: str | None = Field(None, description="关系的简短描述（1-2 句话）")
    chapter_range: list[int] | None = Field(
        None, description="关系出现/形成的章节序号列表，如 [3, 5, 8]；未知可留空"
    )


class EditRelationInput(BaseModel):
    source_name: str = Field(description="用于定位关系的起点实体名称或别名")
    target_name: str = Field(description="用于定位关系的终点实体名称或别名")
    match_relation_type: str | None = Field(
        None,
        description="当两实体间存在多条关系时，用此字段指定要修改的关系类型；只有一条时可留空",
    )
    new_relation_type: str | None = Field(None, description="新的关系类型；None 表示不修改")
    description: str | None = Field(None, description="新的关系描述；None 表示不修改")
    chapter_range: list[int] | None = Field(
        None, description="新的章节序号列表；None 表示不修改"
    )


class DeleteRelationInput(BaseModel):
    source_name: str = Field(description="要删除关系的起点实体名称或别名")
    target_name: str = Field(description="要删除关系的终点实体名称或别名")
    match_relation_type: str | None = Field(
        None,
        description="当两实体间存在多条关系时，用此字段指定要删除的关系类型；只有一条时可留空",
    )


# ── 工具工厂 ──────────────────────────────────────────────────────────────────


def _match_entity(entities: list[Entity], name: str) -> Entity | None:
    """在实体列表中按名称/别名匹配单个实体，支持精确匹配与包含式模糊匹配。"""
    name_lower = name.strip().lower()
    if not name_lower:
        return None
    for ent in entities:
        if ent.name.lower() == name_lower:
            return ent
        if any((al or "").lower() == name_lower for al in (ent.aliases or [])):
            return ent
    for ent in entities:
        if name_lower in ent.name.lower() or ent.name.lower() in name_lower:
            return ent
    return None


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

    # ── 7. create_entity ─────────────────────────────────────────────────────

    @tool(args_schema=CreateEntityInput)
    async def create_entity(
        name: str,
        entity_type: str,
        description: str | None = None,
        aliases: list[str] | None = None,
        attributes_json: str | None = None,
        first_appearance_chapter: int | None = None,
    ) -> str:
        """新建一个实体（人物/地点/组织/物品/概念）。
        创建前会按名称和别名去重，若已存在同名或同别名实体则拒绝创建并提示改用 edit_entity。
        创建后会同步写入向量库，使其可被语义检索到。"""
        from app.agents.base import get_embeddings

        valid = {"character", "organization", "location", "object", "concept"}
        if entity_type not in valid:
            return f"无效的实体类型「{entity_type}」，请使用：{', '.join(valid)}"

        clean_name = name.strip()
        if not clean_name:
            return "实体名称不能为空。"

        # 解析属性 JSON
        attributes: dict[str, Any] = {}
        if attributes_json is not None:
            try:
                parsed = json.loads(attributes_json)
                if not isinstance(parsed, dict):
                    return "attributes_json 必须是 JSON 对象（键值对）。"
                attributes = parsed
            except json.JSONDecodeError:
                return "attributes_json 格式错误，请传入合法 JSON 字符串。"

        clean_aliases = [a.strip() for a in (aliases or []) if a.strip()]

        # 去重检查：名称或别名命中任一已有实体即视为重复
        async with AsyncSessionLocal() as db:
            ent_result = await db.execute(
                select(Entity).where(Entity.book_id == book_id)
            )
            entities = list(ent_result.scalars().all())

        candidate_norms = {clean_name.lower(), *(a.lower() for a in clean_aliases)}
        for ent in entities:
            existing_norms = {ent.name.lower(), *((al or "").lower() for al in (ent.aliases or []))}
            if candidate_norms & existing_norms:
                return (
                    f"实体「{ent.name}」已存在（名称或别名冲突），未创建。"
                    f"如需修改其信息，请改用 edit_entity。"
                )

        async with AsyncSessionLocal() as db:
            new_entity = Entity(
                book_id=book_id,
                name=clean_name,
                aliases=clean_aliases,
                type=entity_type,
                description=description,
                attributes=attributes,
                first_appearance_chapter=first_appearance_chapter,
            )
            db.add(new_entity)
            await db.commit()
            await db.refresh(new_entity)
            new_id = new_entity.id
            ent_name = new_entity.name
            ent_type = new_entity.type
            ent_desc = new_entity.description

            # 同步写入 ChromaDB
            try:
                embed_model = get_embeddings()
                text = f"{ent_name}（{ent_type}）：{ent_desc or '暂无描述'}"
                vec = await asyncio.to_thread(embed_model.embed_documents, [text])
                col = await asyncio.to_thread(get_or_create_collection, ChromaCollections.ENTITIES)
                await asyncio.to_thread(
                    col.upsert,
                    ids=[f"entity_{new_id}"],
                    embeddings=vec,
                    documents=[text],
                    metadatas=[{
                        "book_id": book_id,
                        "entity_id": new_id,
                        "entity_type": ent_type,
                        "entity_name": ent_name,
                    }],
                )
            except Exception as exc:
                logger.warning("新建实体向量写入失败: %s", exc)

        alias_note = f"（别名：{('、'.join(clean_aliases)) or '无'}）"
        return f"已成功创建实体「{ent_name}」[{ent_type}]{alias_note}。"

    # ── 8. edit_entity ───────────────────────────────────────────────────────

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

    # ── 9. edit_anchor ───────────────────────────────────────────────────────

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

    # ── 10. delete_entity ────────────────────────────────────────────────────

    @tool(args_schema=DeleteEntityInput)
    async def delete_entity(entity_name: str) -> str:
        """删除一个实体及其全部关系。支持按名称或别名精确匹配。
        这是不可逆操作：会一并删除该实体作为源或目标的所有关系，并清理向量库。
        执行前应先向用户确认。"""
        name_lower = entity_name.strip().lower()

        async with AsyncSessionLocal() as db:
            ent_result = await db.execute(
                select(Entity).where(Entity.book_id == book_id)
            )
            entities = list(ent_result.scalars().all())

            matched: Entity | None = None
            for ent in entities:
                if ent.name.lower() == name_lower:
                    matched = ent
                    break
                if any((al or "").lower() == name_lower for al in (ent.aliases or [])):
                    matched = ent
                    break

            if not matched:
                return f"未找到实体「{entity_name}」，无法删除。"

            ent_id = matched.id
            ent_name = matched.name

            # 删除关联关系（显式删除，避免依赖数据库级联是否开启）
            rel_result = await db.execute(
                select(Relation).where(
                    Relation.book_id == book_id,
                    or_(Relation.source_id == ent_id, Relation.target_id == ent_id),
                )
            )
            relations = list(rel_result.scalars().all())
            rel_count = len(relations)
            for rel in relations:
                await db.delete(rel)

            target = await db.get(Entity, ent_id)
            if target is not None:
                await db.delete(target)
            await db.commit()

        # 清理 ChromaDB 中的实体向量
        try:
            col = await asyncio.to_thread(get_or_create_collection, ChromaCollections.ENTITIES)
            await asyncio.to_thread(col.delete, ids=[f"entity_{ent_id}"])
        except Exception as exc:
            logger.warning("删除实体向量失败: %s", exc)

        rel_note = f"，并移除了 {rel_count} 条关联关系" if rel_count else ""
        return f"已成功删除实体「{ent_name}」{rel_note}。"

    # ── 11. create_relation ──────────────────────────────────────────────────

    @tool(args_schema=CreateRelationInput)
    async def create_relation(
        source_name: str,
        target_name: str,
        relation_type: str,
        description: str | None = None,
        chapter_range: list[int] | None = None,
    ) -> str:
        """在两个已有实体之间新建一条有向关系（起点 → 终点）。
        起点与终点实体必须已存在（按名称或别名匹配），否则请先用 create_entity 创建。
        若两实体间已存在相同类型的关系则拒绝创建并提示改用 edit_relation。"""
        clean_type = relation_type.strip()
        if not clean_type:
            return "关系类型不能为空。"

        async with AsyncSessionLocal() as db:
            ent_result = await db.execute(
                select(Entity).where(Entity.book_id == book_id)
            )
            entities = list(ent_result.scalars().all())

        source = _match_entity(entities, source_name)
        if source is None:
            return f"未找到起点实体「{source_name}」，请先用 create_entity 创建，或检查名称。"
        target = _match_entity(entities, target_name)
        if target is None:
            return f"未找到终点实体「{target_name}」，请先用 create_entity 创建，或检查名称。"
        if source.id == target.id:
            return "关系的起点和终点不能是同一个实体。"

        clean_range = [int(c) for c in (chapter_range or [])]

        async with AsyncSessionLocal() as db:
            dup_result = await db.execute(
                select(Relation).where(
                    Relation.book_id == book_id,
                    Relation.source_id == source.id,
                    Relation.target_id == target.id,
                    Relation.relation_type == clean_type,
                )
            )
            if dup_result.scalar_one_or_none() is not None:
                return (
                    f"「{source.name} → {target.name}」之间已存在类型为「{clean_type}」的关系，"
                    f"未重复创建。如需修改请改用 edit_relation。"
                )

            new_rel = Relation(
                book_id=book_id,
                source_id=source.id,
                target_id=target.id,
                relation_type=clean_type,
                description=description,
                chapter_range=clean_range,
            )
            db.add(new_rel)
            await db.commit()

        return f"已成功创建关系：[{clean_type}] {source.name} → {target.name}。"

    # ── 12. edit_relation ────────────────────────────────────────────────────

    @tool(args_schema=EditRelationInput)
    async def edit_relation(
        source_name: str,
        target_name: str,
        match_relation_type: str | None = None,
        new_relation_type: str | None = None,
        description: str | None = None,
        chapter_range: list[int] | None = None,
    ) -> str:
        """修改两实体之间已有的关系，支持修改关系类型、描述和章节范围。
        按起点/终点实体名称定位关系（忽略方向）；若两实体间有多条关系，需用 match_relation_type 指定。"""
        if new_relation_type is None and description is None and chapter_range is None:
            return "未提供任何修改内容，关系未变更。"

        async with AsyncSessionLocal() as db:
            ent_result = await db.execute(
                select(Entity).where(Entity.book_id == book_id)
            )
            entities = list(ent_result.scalars().all())

        source = _match_entity(entities, source_name)
        target = _match_entity(entities, target_name)
        if source is None or target is None:
            missing = source_name if source is None else target_name
            return f"未找到实体「{missing}」，无法定位关系。"

        async with AsyncSessionLocal() as db:
            rel_result = await db.execute(
                select(Relation).where(
                    Relation.book_id == book_id,
                    or_(
                        (Relation.source_id == source.id) & (Relation.target_id == target.id),
                        (Relation.source_id == target.id) & (Relation.target_id == source.id),
                    ),
                )
            )
            candidates = list(rel_result.scalars().all())

            if match_relation_type:
                candidates = [r for r in candidates if r.relation_type == match_relation_type.strip()]

            if not candidates:
                return f"未找到「{source.name}」与「{target.name}」之间的关系。"
            if len(candidates) > 1:
                types = "、".join(sorted({r.relation_type for r in candidates}))
                return (
                    f"「{source.name}」与「{target.name}」之间存在多条关系（{types}），"
                    f"请用 match_relation_type 指定要修改的关系类型。"
                )

            rel = await db.get(Relation, candidates[0].id)
            if rel is None:
                return "数据库查询失败，请重试。"

            changed: list[str] = []
            if new_relation_type is not None:
                clean_type = new_relation_type.strip()
                if not clean_type:
                    return "新的关系类型不能为空。"
                rel.relation_type = clean_type
                changed.append("类型")
            if description is not None:
                rel.description = description
                changed.append("描述")
            if chapter_range is not None:
                rel.chapter_range = [int(c) for c in chapter_range]
                changed.append("章节范围")

            await db.commit()

        return f"已成功修改「{source.name} ↔ {target.name}」关系的：{', '.join(changed)}。"

    # ── 13. delete_relation ──────────────────────────────────────────────────

    @tool(args_schema=DeleteRelationInput)
    async def delete_relation(
        source_name: str,
        target_name: str,
        match_relation_type: str | None = None,
    ) -> str:
        """删除两实体之间的一条关系（不影响实体本身）。
        按起点/终点实体名称定位关系（忽略方向）；若两实体间有多条关系，需用 match_relation_type 指定。
        这是不可逆操作，执行前应先向用户确认。"""
        async with AsyncSessionLocal() as db:
            ent_result = await db.execute(
                select(Entity).where(Entity.book_id == book_id)
            )
            entities = list(ent_result.scalars().all())

        source = _match_entity(entities, source_name)
        target = _match_entity(entities, target_name)
        if source is None or target is None:
            missing = source_name if source is None else target_name
            return f"未找到实体「{missing}」，无法定位关系。"

        async with AsyncSessionLocal() as db:
            rel_result = await db.execute(
                select(Relation).where(
                    Relation.book_id == book_id,
                    or_(
                        (Relation.source_id == source.id) & (Relation.target_id == target.id),
                        (Relation.source_id == target.id) & (Relation.target_id == source.id),
                    ),
                )
            )
            candidates = list(rel_result.scalars().all())

            if match_relation_type:
                candidates = [r for r in candidates if r.relation_type == match_relation_type.strip()]

            if not candidates:
                return f"未找到「{source.name}」与「{target.name}」之间的关系，无法删除。"
            if len(candidates) > 1:
                types = "、".join(sorted({r.relation_type for r in candidates}))
                return (
                    f"「{source.name}」与「{target.name}」之间存在多条关系（{types}），"
                    f"请用 match_relation_type 指定要删除的关系类型。"
                )

            rel = candidates[0]
            rel_type = rel.relation_type
            await db.delete(rel)
            await db.commit()

        return f"已成功删除关系：[{rel_type}] {source.name} ↔ {target.name}。"

    # ── 14. get_chapter_text ─────────────────────────────────────────────────

    @tool
    async def get_chapter_text(chapter_number: int) -> str:
        """获取指定章节的完整原文。适用于需要逐字阅读、精确引用或分析章节具体内容的场景。
        若章节过长会被截断，并提示改用 get_chapter_lines 按行数分段读取。"""
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

        raw_text = chapter.raw_text or ""
        total_lines = len(raw_text.splitlines())
        header = (
            f"【第{chapter_number}章原文：{chapter.title or '无标题'}】\n"
            f"（共 {total_lines} 行 / 约 {chapter.word_count} 字）\n\n"
        )

        if len(raw_text) > _MAX_CHAPTER_TEXT:
            body = (
                raw_text[:_MAX_CHAPTER_TEXT]
                + f"\n\n…（全文共 {len(raw_text)} 字、{total_lines} 行，已截断；"
                f"如需阅读后续内容，请用 get_chapter_lines 指定行数范围）"
            )
        else:
            body = raw_text

        return header + body

    # ── 15. get_chapter_lines ────────────────────────────────────────────────

    @tool
    async def get_chapter_lines(
        chapter_number: int, start_line: int, end_line: int
    ) -> str:
        """获取指定章节中某一行数范围的原文（行号从 1 开始，含起止行）。
        适用于精确定位、逐行引用，或在章节过长时分段读取原文。
        单次最多返回 200 行，超出会自动收窄范围。"""
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

        lines = (chapter.raw_text or "").splitlines()
        total = len(lines)
        if total == 0:
            return f"第{chapter_number}章原文为空。"

        if end_line < start_line:
            start_line, end_line = end_line, start_line
        start_line = max(1, start_line)
        if start_line > total:
            return f"第{chapter_number}章共 {total} 行，起始行 {start_line} 已超出范围。"
        end_line = min(end_line, total, start_line + _MAX_LINE_SPAN - 1)

        selected = lines[start_line - 1 : end_line]
        width = len(str(end_line))
        numbered = "\n".join(
            f"{start_line + i:>{width}} | {line}" for i, line in enumerate(selected)
        )

        return (
            f"【第{chapter_number}章原文 第{start_line}-{end_line}行 / 共{total}行：{chapter.title or '无标题'}】\n\n"
            f"{numbered}"
        )

    return [
        search_knowledge,
        get_entity,
        get_chapter_anchor,
        get_timeline,
        get_entity_relations,
        search_chapters,
        create_entity,
        edit_entity,
        edit_anchor,
        delete_entity,
        create_relation,
        edit_relation,
        delete_relation,
        get_chapter_text,
        get_chapter_lines,
    ]
