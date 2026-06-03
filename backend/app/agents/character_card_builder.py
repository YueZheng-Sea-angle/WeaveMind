"""
Character Card Builder Agent

在章节分析时自动创建 / 更新「关键角色卡」：识别本章重点角色，
为其维护生平、性格特点、人物关系、技能、道具、当前状态、关键伏笔等结构化条目。

设计要点：
- 增量更新而非从零重建：调用 LLM 前先把「截至上一章的累积角色卡状态」连同本章锚点、
  已知人物实体一并作为上下文发送给 Agent，使其能在已有内容基础上做补充、更新、揭露。
- 顺序依赖：orchestrator 逐章顺序处理（每章 extract→anchor→cards→commit 后才进入下一章），
  因此处理第 X 章时第 X-1 章的角色卡已落库；角色卡为全书累积，当前 DB 状态即「截至 X-1 章」的状态。

与对话大脑职责区分（启用/停用维度的保护）：
- 本 Agent 只负责内容（卡片与条目的增改），绝不修改任何 enabled 状态。
- 去重时会比对该卡片下「全部」条目（含已停用），因此不会重新引入用户主动停用的条目。
- 对命中的、当前启用中的同名条目可刷新其正文；对已停用的同名条目则原样跳过，尊重用户停用意图。
"""

from __future__ import annotations

import asyncio
import logging

from langchain.output_parsers import PydanticOutputParser
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.base import get_processing_llm, build_robust_parser
from app.models.chapter import ChapterAnchor
from app.models.character_card import (
    CATEGORY_LABELS,
    VALID_CATEGORIES,
    CharacterCard,
    CharacterCardEntry,
)
from app.models.entity import Entity, EntityType
from app.tools.chat_tools import _match_entity

logger = logging.getLogger(__name__)

MAX_CHAPTER_CHARS = 8000
MAX_CARDS_CONTEXT_CHARS = 8000
MAX_ENTITIES_CONTEXT = 40


# ── LLM 结构化输出 Schema ────────────────────────────────────────────────────

class CardEntryDraft(BaseModel):
    category: str = Field(
        description=(
            "条目分类，必须是以下之一：biography（生平）/ personality（性格特点）/ "
            "relationship（人物关系）/ skill（技能）/ item（道具）/ status（当前状态）/ "
            "foreshadowing（关键伏笔）"
        )
    )
    title: str = Field(
        description=(
            "条目标题，简短，如技能名、道具名、关系对象名、伏笔简称等。"
            "若是对【已有角色卡】里某条目的补充/更新/揭露，请沿用其原标题以便对齐。"
        )
    )
    content: str = Field(description="条目正文（更新后的完整描述），一到三句话")


class CharacterCardDraft(BaseModel):
    name: str = Field(
        description="重点角色的规范名称（与【已有角色卡】中名称保持一致，便于对齐到同一张卡片）"
    )
    summary: str = Field(description="该角色截至本章的一句话简介")
    entries: list[CardEntryDraft] = Field(
        default=[],
        description=(
            "该角色【在本章新增或需要更新】的结构化条目；"
            "无变化的旧条目不必重复列出"
        ),
    )


class CardBuildResult(BaseModel):
    characters: list[CharacterCardDraft] = Field(
        default=[],
        description="本章出场或被实质提及、值得维护角色卡的重点角色（次要/路人角色不必列出）",
    )


def _norm(s: str) -> str:
    return (s or "").strip().lower()


# ── 上下文渲染 ───────────────────────────────────────────────────────────────

def _render_one_card(card: CharacterCard) -> str:
    """把单张角色卡（仅启用中的条目）渲染为可读文本块。"""
    lines = [f"### {card.name}"]
    if card.summary:
        lines.append(f"简介：{card.summary}")
    enabled_entries = [e for e in card.entries if e.enabled]
    if not enabled_entries:
        lines.append("（暂无条目）")
    else:
        for cat in CATEGORY_LABELS:
            items = [e for e in enabled_entries if e.category == cat]
            if not items:
                continue
            lines.append(f"- {CATEGORY_LABELS[cat]}：")
            for e in items:
                lines.append(f"    · {e.title}：{e.content or '（无内容）'}")
    return "\n".join(lines)


def _render_existing_cards(
    cards: list[CharacterCard], focus_names: list[str]
) -> str:
    """渲染已有角色卡上下文；本章涉及的角色（focus）优先靠前，超长则截断。"""
    enabled_cards = [c for c in cards if c.enabled]
    if not enabled_cards:
        return "（当前尚无任何关键角色卡，本章可按需新建）"

    focus_norm = {_norm(n) for n in focus_names if n}

    def is_focus(c: CharacterCard) -> bool:
        cn = _norm(c.name)
        if cn in focus_norm:
            return True
        return any(fn and (fn in cn or cn in fn) for fn in focus_norm)

    ordered = sorted(enabled_cards, key=lambda c: (not is_focus(c), c.name))

    blocks: list[str] = []
    total = 0
    truncated = False
    for card in ordered:
        block = _render_one_card(card)
        if total + len(block) > MAX_CARDS_CONTEXT_CHARS and blocks:
            truncated = True
            break
        blocks.append(block)
        total += len(block)

    text = "\n\n".join(blocks)
    if truncated:
        text += "\n\n…（其余角色卡因篇幅省略）"
    return text


def _render_anchor(anchor: ChapterAnchor | None, chapter_number: int) -> str:
    if anchor is None:
        return "（本章锚点尚未生成）"
    parts: list[str] = []
    if anchor.summary:
        parts.append(f"摘要：{anchor.summary}")
    if anchor.characters_present:
        parts.append("出场人物：" + "、".join(anchor.characters_present))
    if anchor.key_events:
        parts.append(
            "关键事件：\n"
            + "\n".join(f"  - {e}" for e in anchor.key_events)
        )
    if anchor.foreshadowing:
        parts.append(
            "伏笔线索：\n"
            + "\n".join(f"  - {f}" for f in anchor.foreshadowing)
        )
    return "\n".join(parts) if parts else f"（第{chapter_number}章锚点内容为空）"


def _render_character_entities(entities: list[Entity]) -> str:
    chars = [e for e in entities if e.type == EntityType.CHARACTER.value]
    if not chars:
        return "（暂无已登记的人物实体）"
    lines: list[str] = []
    for e in chars[:MAX_ENTITIES_CONTEXT]:
        alias = f"（别名：{'、'.join(e.aliases)}）" if e.aliases else ""
        lines.append(f"- {e.name}{alias}")
    if len(chars) > MAX_ENTITIES_CONTEXT:
        lines.append(f"…（共 {len(chars)} 个人物，仅列出前 {MAX_ENTITIES_CONTEXT} 个）")
    return "\n".join(lines)


# ── 核心构建函数 ─────────────────────────────────────────────────────────────

async def update_character_cards_for_chapter(
    chapter_id: int,
    chapter_number: int,
    chapter_text: str,
    book_id: int,
    db: AsyncSession,
) -> None:
    """根据单章内容、并结合截至上一章的累积角色卡状态，增量更新关键角色卡。

    出错会被 orchestrator / reprocess 的 try 捕获；本函数内部对数据库写入尽力而为，
    不影响章节其余分析流程。
    """
    text = chapter_text[:MAX_CHAPTER_CHARS]

    # ── 1) 先加载上下文：已有角色卡（截至上一章）、本章锚点、人物实体 ───────────
    cards_result = await db.execute(
        select(CharacterCard)
        .where(CharacterCard.book_id == book_id)
        .options(selectinload(CharacterCard.entries))
    )
    existing_cards: list[CharacterCard] = list(cards_result.scalars().all())
    card_by_name: dict[str, CharacterCard] = {_norm(c.name): c for c in existing_cards}

    ent_result = await db.execute(select(Entity).where(Entity.book_id == book_id))
    entities = list(ent_result.scalars().all())

    anchor_result = await db.execute(
        select(ChapterAnchor).where(ChapterAnchor.chapter_id == chapter_id)
    )
    anchor = anchor_result.scalar_one_or_none()

    focus_names = list(anchor.characters_present) if anchor and anchor.characters_present else []

    cards_ctx = _render_existing_cards(existing_cards, focus_names)
    anchor_ctx = _render_anchor(anchor, chapter_number)
    entities_ctx = _render_character_entities(entities)

    # ── 2) 组织 prompt：把多维上下文交给 Agent，引导其做增量更新 ──────────────
    llm = get_processing_llm()
    parser = PydanticOutputParser(pydantic_object=CardBuildResult)

    system_content = (
        "你是一个专业的文学分析助手，负责为长篇小说持续维护「关键角色卡」——重点角色的结构化档案。\n"
        "你会拿到【已有关键角色卡】（截至上一章的累积状态）、【本章锚点】、【已知人物实体】和【本章正文】。\n"
        "你的任务是：对照已有角色卡，判断本章为各重点角色带来的变化，做【增量更新】。\n\n"
        "分类含义：\n"
        "- biography（生平）：身世、经历、重要往事\n"
        "- personality（性格特点）：性格、价值观、行为倾向\n"
        "- relationship（人物关系）：与其他角色的关系，title 用对方名字\n"
        "- skill（技能）：能力、武功、专长，title 用技能名\n"
        "- item（道具）：持有的关键物品，title 用道具名\n"
        "- status（当前状态）：本章结束时该角色的最新处境、身体/心理状态、目标\n"
        "- foreshadowing（关键伏笔）：与该角色相关、本章埋下或被揭示的伏笔/悬念\n\n"
        "更新原则：\n"
        "1. 只输出本章【出场或被实质提及】的角色；与已有角色卡同一人时，name 必须沿用已有名称。\n"
        "2. 区分三类变化并据此组织 entries：\n"
        "   - 新增：本章首次出现的信息 → 用新的 title。\n"
        "   - 补充/更新/揭露：本章丰富或改变了已有条目（如身世揭露、关系演变、能力升级）"
        "→ 沿用该条目的原 title，给出更新后的完整 content。\n"
        "   - status（当前状态）应覆盖为本章结束时的最新状态。\n"
        "3. 不要重复列出本章没有变化的旧条目；没有任何变化的角色可不输出。\n"
        "4. 只写本章有明确依据的信息，不臆测、不剧透尚未发生的内容。\n"
        "5. title 简短且在同一分类下唯一，content 一到三句话。\n\n"
        + parser.get_format_instructions()
    )

    prior_label = (
        f"截至第 {chapter_number - 1} 章的累积状态"
        if chapter_number > 1
        else "本章为起始章，暂无往期累积"
    )
    human_content = (
        f"【已有关键角色卡（{prior_label}）】\n{cards_ctx}\n\n"
        f"【本章锚点（第 {chapter_number} 章）】\n{anchor_ctx}\n\n"
        f"【已知人物实体（命名参考）】\n{entities_ctx}\n\n"
        f"【本章正文（第 {chapter_number} 章）】\n{text}\n\n"
        "请基于以上信息，输出本章对关键角色卡的增量更新。"
    )

    messages = [
        SystemMessage(content=system_content),
        HumanMessage(content=human_content),
    ]

    chain = llm | build_robust_parser(parser, llm)
    result: CardBuildResult = await asyncio.to_thread(chain.invoke, messages)

    if not result.characters:
        logger.info("第 %d 章未产出关键角色卡更新", chapter_number)
        return

    # ── 3) 落库：增量合并，保护启用/停用状态 ─────────────────────────────────
    created_cards = 0
    added_entries = 0
    updated_entries = 0

    for draft in result.characters:
        clean_name = draft.name.strip()
        if not clean_name:
            continue

        card = card_by_name.get(_norm(clean_name))
        if card is None:
            matched_ent = _match_entity(entities, clean_name)
            card = CharacterCard(
                book_id=book_id,
                name=clean_name,
                summary=draft.summary or None,
                entity_id=matched_ent.id if matched_ent else None,
            )
            db.add(card)
            await db.flush()
            await db.refresh(card)
            card.entries = []  # type: ignore[attr-defined]
            card_by_name[_norm(clean_name)] = card
            created_cards += 1
        else:
            # 简介随剧情演进更新（内容维度由 Agent 维护；启用/停用维度始终由用户掌控）
            if draft.summary and card.summary != draft.summary:
                card.summary = draft.summary

        existing_by_key: dict[tuple[str, str], CharacterCardEntry] = {
            (e.category, _norm(e.title)): e for e in (card.entries or [])
        }
        max_order: dict[str, int] = {}
        for e in card.entries or []:
            max_order[e.category] = max(max_order.get(e.category, -1), e.sort_order)

        for ed in draft.entries:
            if ed.category not in VALID_CATEGORIES:
                continue
            clean_title = ed.title.strip()
            if not clean_title:
                continue

            key = (ed.category, _norm(clean_title))
            existing_entry = existing_by_key.get(key)

            if existing_entry is not None:
                # 已停用条目：尊重用户停用意图，完全跳过
                if not existing_entry.enabled:
                    continue
                # 启用中的同名条目：刷新正文（不改动 enabled），仅在内容有变化时更新
                if ed.content and existing_entry.content != ed.content:
                    existing_entry.content = ed.content
                    updated_entries += 1
                continue

            new_order = max_order.get(ed.category, -1) + 1
            max_order[ed.category] = new_order
            new_entry = CharacterCardEntry(
                card_id=card.id,
                category=ed.category,
                title=clean_title,
                content=ed.content or None,
                sort_order=new_order,
            )
            db.add(new_entry)
            existing_by_key[key] = new_entry
            added_entries += 1

    await db.flush()
    logger.info(
        "第 %d 章关键角色卡更新完成：涉及 %d 个角色，新建卡片 %d，新增条目 %d，更新条目 %d",
        chapter_number,
        len(result.characters),
        created_cards,
        added_entries,
        updated_entries,
    )
