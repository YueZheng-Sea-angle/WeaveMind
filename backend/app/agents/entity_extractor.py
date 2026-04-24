"""
Entity Extractor Agent

逐章提取人物、组织、地点、物品、概念及其相互关系，
跨章节累积去重后写入数据库与 ChromaDB 向量库。
"""

import asyncio
import logging
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.entity import Entity, Relation, EntityType
from app.agents.base import get_processing_llm, get_embeddings
from app.db.chroma_client import get_or_create_collection, ChromaCollections

logger = logging.getLogger(__name__)

MAX_CHAPTER_CHARS = 8000


# ── LLM 结构化输出 Schema ────────────────────────────────────────────────────

class ExtractedEntity(BaseModel):
    name: str = Field(description="实体的规范名称（人物用全名或最常用称呼）")
    type: str = Field(description="实体类型，必须是以下之一：character / organization / location / object / concept")
    aliases: list[str] = Field(default=[], description="该实体的别名、绰号、简称、外号等")
    description: str = Field(description="对该实体的简短描述（1-3句话），概括其身份、特征或作用")
    attributes: dict[str, Any] = Field(default={}, description="额外属性，如性别、年龄、职业、外貌特征等键值对")


class ExtractedRelation(BaseModel):
    source: str = Field(description="关系源实体的名称（需与 entities 中的 name 一致）")
    target: str = Field(description="关系目标实体的名称（需与 entities 中的 name 一致）")
    relation_type: str = Field(description="关系类型，如：父子、师徒、盟友、敌对、夫妻、主仆等")
    description: str = Field(description="对该关系的一句话描述")


class ExtractionResult(BaseModel):
    entities: list[ExtractedEntity] = Field(description="从本章节提取的所有实体，不重不漏")
    relations: list[ExtractedRelation] = Field(description="实体间的关系，仅包含本章明确提及的关系")


# ── 工具函数 ─────────────────────────────────────────────────────────────────

def _normalize(name: str) -> str:
    return name.strip().lower()


VALID_ENTITY_TYPES = {e.value for e in EntityType}


# ── 核心提取函数 ─────────────────────────────────────────────────────────────

async def extract_entities_for_chapter(
    chapter_id: int,
    chapter_number: int,
    chapter_text: str,
    book_id: int,
    db: AsyncSession,
) -> None:
    """
    对单章执行实体提取并写入数据库与向量库。

    - 使用 LLM structured output 提取结构化实体和关系
    - 与本书已有实体进行名称/别名匹配去重
    - 新实体写入 entities 表，已有实体合并别名和描述
    - 关系写入 relations 表，已有关系更新 chapter_range
    - 实体描述向量化后写入 ChromaDB
    """
    text = chapter_text[:MAX_CHAPTER_CHARS]

    llm = get_processing_llm()
    structured_llm = llm.with_structured_output(ExtractionResult)

    messages = [
        (
            "system",
            (
                "你是一个专业的文学分析助手，负责从小说章节中提取结构化信息。\n"
                "规则：\n"
                "- 只提取章节中明确出现或被提及的实体\n"
                "- type 必须是以下之一：character / organization / location / object / concept\n"
                "- 人物用最完整、最常用的名称作为 name，其余称呼放入 aliases\n"
                "- 关系仅列出本章文本中有依据的关系，不推测\n"
                "- 描述简洁，控制在 1-3 句话以内"
            ),
        ),
        (
            "human",
            f"请分析以下小说章节（第 {chapter_number} 章），提取实体和关系：\n\n{text}",
        ),
    ]

    result: ExtractionResult = await asyncio.to_thread(structured_llm.invoke, messages)

    # ── 加载本书现有实体，构建去重查找表 ────────────────────────────────────
    existing_result = await db.execute(
        select(Entity).where(Entity.book_id == book_id)
    )
    existing_entities: list[Entity] = list(existing_result.scalars().all())

    entity_lookup: dict[str, Entity] = {}
    for ent in existing_entities:
        entity_lookup[_normalize(ent.name)] = ent
        for alias in (ent.aliases or []):
            entity_lookup[_normalize(alias)] = ent

    name_to_db_entity: dict[str, Entity] = {}

    # ── 实体去重与写入 ────────────────────────────────────────────────────────
    for extracted in result.entities:
        norm_name = _normalize(extracted.name)
        all_norms = [norm_name] + [_normalize(a) for a in extracted.aliases]

        matched: Entity | None = None
        for n in all_norms:
            if n in entity_lookup:
                matched = entity_lookup[n]
                break

        if matched:
            # 合并别名
            existing_aliases: set[str] = set(matched.aliases or [])
            new_aliases = (set(extracted.aliases) | {extracted.name}) - {matched.name}
            merged_aliases = list(existing_aliases | new_aliases)
            matched.aliases = merged_aliases

            # 若原描述为空则补充
            if not matched.description and extracted.description:
                matched.description = extracted.description
            if extracted.attributes and not matched.attributes:
                matched.attributes = extracted.attributes

            name_to_db_entity[extracted.name] = matched
            # 更新查找表
            for alias in merged_aliases:
                entity_lookup[_normalize(alias)] = matched

        else:
            entity_type = (
                extracted.type if extracted.type in VALID_ENTITY_TYPES
                else EntityType.CHARACTER.value
            )
            new_entity = Entity(
                book_id=book_id,
                name=extracted.name,
                aliases=extracted.aliases,
                type=entity_type,
                description=extracted.description,
                attributes=extracted.attributes,
                first_appearance_chapter=chapter_number,
            )
            db.add(new_entity)
            await db.flush()
            await db.refresh(new_entity)

            name_to_db_entity[extracted.name] = new_entity
            entity_lookup[norm_name] = new_entity
            for alias in extracted.aliases:
                entity_lookup[_normalize(alias)] = new_entity

    # ── 关系写入 ─────────────────────────────────────────────────────────────
    def _resolve(name: str) -> Entity | None:
        if name in name_to_db_entity:
            return name_to_db_entity[name]
        return entity_lookup.get(_normalize(name))

    for extracted_rel in result.relations:
        source = _resolve(extracted_rel.source)
        target = _resolve(extracted_rel.target)
        if not source or not target:
            continue

        existing_rel_result = await db.execute(
            select(Relation).where(
                Relation.book_id == book_id,
                Relation.source_id == source.id,
                Relation.target_id == target.id,
                Relation.relation_type == extracted_rel.relation_type,
            )
        )
        existing_rel = existing_rel_result.scalar_one_or_none()

        if existing_rel:
            chapter_range: list[int] = list(existing_rel.chapter_range or [])
            if chapter_number not in chapter_range:
                chapter_range.append(chapter_number)
                existing_rel.chapter_range = sorted(chapter_range)
        else:
            db.add(
                Relation(
                    book_id=book_id,
                    source_id=source.id,
                    target_id=target.id,
                    relation_type=extracted_rel.relation_type,
                    description=extracted_rel.description,
                    chapter_range=[chapter_number],
                )
            )

    await db.flush()

    # ── ChromaDB 实体向量写入 ─────────────────────────────────────────────────
    entities_to_embed = list(name_to_db_entity.values())
    if not entities_to_embed:
        return

    try:
        embed_model = get_embeddings()
        texts = [
            f"{e.name}（{e.type}）：{e.description or '暂无描述'}"
            for e in entities_to_embed
        ]
        vectors = await asyncio.to_thread(embed_model.embed_documents, texts)
        collection = await asyncio.to_thread(
            get_or_create_collection, ChromaCollections.ENTITIES
        )
        await asyncio.to_thread(
            collection.upsert,
            ids=[f"entity_{e.id}" for e in entities_to_embed],
            embeddings=vectors,
            documents=texts,
            metadatas=[
                {
                    "book_id": book_id,
                    "entity_id": e.id,
                    "entity_type": e.type,
                    "entity_name": e.name,
                }
                for e in entities_to_embed
            ],
        )
    except Exception:
        logger.warning(
            "ChromaDB 实体向量写入失败（章节 %d），继续处理",
            chapter_number,
            exc_info=True,
        )
