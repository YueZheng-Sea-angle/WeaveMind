"""
Character Card Builder Agent

在章节分析时自动创建 / 更新「关键角色卡」：识别本章重点角色，
为其维护生平、性格特点、人物关系、技能、道具、当前状态、关键伏笔等结构化条目。

设计要点：
- 增量更新而非从零重建：调用 LLM 前先把「截至上一章的累积角色卡状态」连同本章锚点、
  已知人物实体一并作为上下文发送给 Agent，使其能在已有内容基础上做补充、更新、揭露。
- 顺序依赖：orchestrator 逐章顺序处理（每章 extract→anchor→cards→commit 后才进入下一章），
  因此处理第 X 章时第 X-1 章的角色卡已落库；角色卡为全书累积，当前 DB 状态即「截至 X-1 章」的状态。

条目操作（add / update / delete）：
- add：本章首次出现的新信息，新建条目。
- update：按条目 id 命中【已有条目】，刷新其正文（必要时改标题），用于身世揭露、关系演变、能力升级、状态推进等同一条目的内容演进。
- delete：把【易过时】类别（status / foreshadowing）中已过时/已兑现的条目软停用（enabled=False），用于清理而非物理删除——条目仍留库、用户可在前端重新启用。
  较稳定的类别（生平 / 性格 / 关系 / 技能 / 道具）不允许 builder delete，过时也只用 update 改写。

与对话大脑职责区分（启用/停用维度）：
- 上下文只渲染「启用中」的条目并为每条带上 [#id]，因此被（用户或 builder）停用的条目下一章起 builder 不再可见，避免上下文污染，也不会被重新引入。
- builder 的 add/update 只作用于启用中的条目；用户主动停用的条目 builder 看不到、尊重其停用意图。builder 自身只在 status / foreshadowing 两类上行使停用权。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator

from langchain.output_parsers import PydanticOutputParser
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.base import get_card_builder_llm, build_robust_parser
from app.db.database import AsyncSessionLocal
from app.models.book import Book
from app.models.chapter import Chapter, ChapterAnchor
from app.models.character_card import (
    CATEGORY_LABELS,
    VALID_CATEGORIES,
    CharacterCard,
    CharacterCardCategory,
    CharacterCardEntry,
)
from app.models.entity import Entity, EntityType
from app.tools.chat_tools import _match_entity

logger = logging.getLogger(__name__)

MAX_CHAPTER_CHARS = 8000
MAX_CARDS_CONTEXT_CHARS = 8000
MAX_ENTITIES_CONTEXT = 40

# 仅「易过时」类别允许 builder 软停用（delete）；其余较稳定类别只能新增/更新。
DELETABLE_CATEGORIES = {
    CharacterCardCategory.STATUS.value,
    CharacterCardCategory.FORESHADOWING.value,
}


# ── LLM 结构化输出 Schema ────────────────────────────────────────────────────

class CardEntryOp(BaseModel):
    action: str = Field(
        default="add",
        description=(
            "对条目执行的操作，必须是以下之一：\n"
            "- add：新增一条本章首次出现的信息（需给 category/title/content，不要填 entry_id）；\n"
            "- update：更新【已有条目】的正文/标题（必须用 entry_id 指向上下文里该条目的 [#id]，给出更新后完整 content；如需改标题再给 title）；\n"
            "- delete：作废一条已过时/已兑现的条目（必须用 entry_id 指向 [#id]）。仅 status 与 foreshadowing 两类允许 delete，其余类别请改用 update。"
        ),
    )
    entry_id: int | None = Field(
        default=None,
        description=(
            "update / delete 时必填：上下文【已有角色卡】中每条前方括号里的数字（如 [#142] 则填 142）。add 时留空。"
        ),
    )
    category: str | None = Field(
        default=None,
        description=(
            "add 时必填。条目分类，必须是以下之一：biography（生平）/ personality（性格特点）/ "
            "relationship（人物关系）/ skill（技能）/ item（道具）/ status（当前状态）/ "
            "foreshadowing（剧情线索）"
        ),
    )
    title: str | None = Field(
        default=None,
        description=(
            "add 时必填的条目标题（简短，如技能名、道具名、关系对象名、伏笔简称等）；"
            "update 时若需调整标题可一并给出，否则留空沿用原标题。"
        ),
    )
    content: str | None = Field(
        default=None,
        description="add / update 时的条目正文（更新后的完整描述），一到三句话；delete 时可留空。",
    )


class CharacterCardDraft(BaseModel):
    name: str = Field(
        description="重点角色的规范名称（与【已有角色卡】中名称保持一致，便于对齐到同一张卡片）"
    )
    summary: str = Field(description="该角色截至本章的一句话简介")
    operations: list[CardEntryOp] = Field(
        default=[],
        description=(
            "该角色【在本章需要落地的条目变更操作】列表（新增 / 更新 / 删除）；"
            "本章没有变化的条目不要列出"
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
                lines.append(f"    · [#{e.id}] {e.title}：{e.content or '（无内容）'}")
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
    llm = get_card_builder_llm()
    parser = PydanticOutputParser(pydantic_object=CardBuildResult)

    system_content = (
        "你是一个专业的文学分析助手，负责为长篇小说持续维护「关键角色卡」——重点角色的结构化档案。\n"
        "你会拿到【已有关键角色卡】（截至上一章的累积状态，其中每个条目前用 [#id] 标注唯一编号）、【本章锚点】、【已知人物实体】和【本章正文】。\n"
        "你的任务是：对照已有角色卡，判断本章为各重点角色带来的变化，输出一组【条目操作】（add 新增 / update 更新 / delete 删除）做增量维护。\n\n"
        "分类含义：\n"
        "- biography（生平）：身世、经历、重要往事。无需记录鸡毛蒜皮的临时小事。\n"
        "- personality（性格特点）：性格、价值观、行为倾向。只记录明确反映出的永久性/代表性性格，不要记录临时的情绪。\n"
        "- relationship（人物关系）：与其他角色的关系，title 用对方名字\n"
        "- skill（技能）：能力、武功、专长，title 用技能名\n"
        "- item（道具）：持有的关键物品，title 用道具名\n"
        "- status（当前状态）：本章结束时该角色的最新处境、身体/心理状态。只注重时间、空间上的状态，与下面的【剧情线索】区分开。\n"
        "- foreshadowing（剧情线索）：1.该角色接下来可能要去做的事（区分并注明短期/长期，如：计划调查XXX的资料；有XXX的任务需要完成；将在三天后参与XXX大赛等。）；2.与该角色【直接关联】的伏笔/悬念。直接关联的定义：该伏笔可能对该角色本人产生重大影响，且与该角色本人的秘密/决策/命运直接相关。\n\n"
        "三种操作（action）的用法：\n"
        "- add：本章首次出现的新信息 → 给出 category/title/content，entry_id 留空。\n"
        "- update：本章丰富或改变了某条【已有条目】（如身世揭露、关系演变、能力升级、状态推进）→ 用 entry_id 指向该条目的 [#id]，给出更新后的【完整】content；如需调整标题再给 title。同一条目内容演进时务必用 update，不要再 add 一条造成重复。\n"
        "- delete：某条目已过时 / 已兑现 / 不再成立 → 用 entry_id 指向其 [#id]。注意：仅 status（当前状态）与 foreshadowing（剧情线索）两类允许 delete；biography / personality / relationship / skill / item 属较稳定信息，过时也只用 update 改写，禁止 delete。\n\n"
        "更新原则：\n"
        "1. 只输出本章【出场或被实质提及】的角色；与已有角色卡同一人时，name 必须沿用已有名称。\n"
        "2. status（当前状态）应覆盖为本章结束时的最新状态：状态有推进时优先 update 已有那条 status。应注明status出现章数，使用【第X章结束时】作为固定前缀。status下不允许存在超过2条非过时状态，如果存在，应及时对已过时的status执行 delete，或尝试合并状态。如果你看到某个角色有多条status，请检查是否有过时status并 delete。你应相信所有status在上一章均未过时，只检查本章是否可能导致存在过时status。\n"
        "3. foreshadowing（剧情线索）应覆盖为本章结束时的最新剧情线索。请注意已经揭露/爆发的线索、已经达成的目的将不再是线索，如第5章的线索是角色接下来要去调查X区域，第7章角色调查了X区域，那第5章的线索已失效，你应对其执行 delete。如果你看到某个角色有多条foreshadowing，请检查是否有过时foreshadowing并 delete。你应相信所有foreshadowing在上一章均未过时，只检查本章是否可能导致存在过时foreshadowing。\n"
        "4. 不要输出本章没有变化的条目；没有任何变化的角色可不输出。\n"
        "5. 只写本章有明确依据的信息，不臆测、不剧透尚未发生的内容。\n"
        "6. title 简短且在同一分类下唯一，content 一到三句话。\n"
        "7. 对于同一个角色的多种身份，如果你判断它们的性格、关系线等内容迥异，应分开建卡。\n"
        "8. 当你需要指代你处理的这一章时，不要使用【本章】这类关键词，需要明确标注你处理的这一章的具体章节，以便后续agent识别、区分。\n\n"
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
    disabled_entries = 0

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
            # 在对象仍为 transient 时即把 entries 初始化为「已加载的空集合」，
            # 避免 flush 后再访问/赋值该关系触发隐式懒加载 SELECT
            # （在 async 会话的同步上下文中会抛 greenlet_spawn 错误）。
            card.entries = []  # type: ignore[attr-defined]
            db.add(card)
            await db.flush()  # 仅为拿到 card.id；不要再 refresh，否则会过期并触发懒加载
            card_by_name[_norm(clean_name)] = card
            created_cards += 1
        else:
            # 简介随剧情演进更新（内容维度由 Agent 维护；启用/停用维度始终由用户掌控）
            if draft.summary and card.summary != draft.summary:
                card.summary = draft.summary

        existing_by_key: dict[tuple[str, str], CharacterCardEntry] = {
            (e.category, _norm(e.title)): e for e in (card.entries or [])
        }
        existing_by_id: dict[int, CharacterCardEntry] = {
            e.id: e for e in (card.entries or []) if e.id is not None
        }
        max_order: dict[str, int] = {}
        for e in card.entries or []:
            max_order[e.category] = max(max_order.get(e.category, -1), e.sort_order)

        for op in draft.operations:
            action = (op.action or "add").strip().lower()

            # ── delete：仅对易过时类别软停用（enabled=False），物理保留可恢复 ──
            if action == "delete":
                if op.entry_id is None:
                    continue
                target = existing_by_id.get(op.entry_id)
                # 命中不到（幻觉 id / 跨卡引用）或本就停用：跳过
                if target is None or not target.enabled:
                    continue
                # 稳定类别不允许 builder 停用，忽略此操作
                if target.category not in DELETABLE_CATEGORIES:
                    continue
                target.enabled = False
                disabled_entries += 1
                continue

            # ── update：按 id 命中已有条目，刷新正文（必要时改标题），不改 enabled ──
            if action == "update":
                if op.entry_id is None:
                    continue
                target = existing_by_id.get(op.entry_id)
                if target is None or not target.enabled:
                    continue
                changed = False
                if op.content and target.content != op.content:
                    target.content = op.content
                    changed = True
                if op.title:
                    new_title = op.title.strip()
                    if new_title and new_title != target.title:
                        # 同步维护 (category, title) 索引，避免后续 add 误判重复
                        existing_by_key.pop((target.category, _norm(target.title)), None)
                        target.title = new_title
                        existing_by_key[(target.category, _norm(new_title))] = target
                        changed = True
                if changed:
                    updated_entries += 1
                continue

            # ── add（默认）：新增条目，按 (category, title) 去重 ──────────────────
            if op.category not in VALID_CATEGORIES:
                continue
            clean_title = (op.title or "").strip()
            if not clean_title:
                continue

            key = (op.category, _norm(clean_title))
            existing_entry = existing_by_key.get(key)
            if existing_entry is not None:
                # 已停用的同名条目：尊重停用意图，跳过
                if not existing_entry.enabled:
                    continue
                # 启用中的同名条目：等价于一次 update，仅在内容有变化时刷新正文
                if op.content and existing_entry.content != op.content:
                    existing_entry.content = op.content
                    updated_entries += 1
                continue

            new_order = max_order.get(op.category, -1) + 1
            max_order[op.category] = new_order
            new_entry = CharacterCardEntry(
                card_id=card.id,
                category=op.category,
                title=clean_title,
                content=op.content or None,
                sort_order=new_order,
            )
            db.add(new_entry)
            existing_by_key[key] = new_entry
            added_entries += 1

    await db.flush()
    logger.info(
        "第 %d 章关键角色卡更新完成：涉及 %d 个角色，新建卡片 %d，新增条目 %d，更新条目 %d，停用条目 %d",
        chapter_number,
        len(result.characters),
        created_cards,
        added_entries,
        updated_entries,
        disabled_entries,
    )


# ── 一键建立：逐章流式构建 ───────────────────────────────────────────────────

def _sse(event: str, data: dict) -> str:
    """格式化为 SSE 消息字符串。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def build_character_cards_stream(book_id: int) -> AsyncGenerator[str, None]:
    """对全书逐章顺序运行角色卡构建（「一键建立」），以 SSE 形式推送进度。

    适用于本功能上线前已存在、尚无角色卡的旧书库：仅构建/更新关键角色卡，
    不重跑实体提取与锚点。逐章顺序保证第 X 章构建时已包含截至 X-1 章的累积状态。

    SSE 事件：
        start          - 开始，携带总章节数
        progress       - 单章进度（status: "processing" | "done"）
        chapter_error  - 单章失败信息（继续后续章节）
        complete       - 全部完成
        error          - 致命错误
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
                yield _sse("error", {"message": "该书暂无章节，请先上传并分章"})
                return

            total = len(chapters)
            yield _sse("start", {"total": total, "message": f"开始建立角色卡，共 {total} 章"})

            failed_chapters: list[int] = []
            processed = 0

            for chapter in chapters:
                ch_num = chapter.chapter_number
                ch_title = chapter.title or f"第{ch_num}章"

                yield _sse(
                    "progress",
                    {
                        "chapter_number": ch_num,
                        "chapter_title": ch_title,
                        "status": "processing",
                        "processed": processed,
                        "total": total,
                    },
                )

                try:
                    await update_character_cards_for_chapter(
                        chapter_id=chapter.id,
                        chapter_number=ch_num,
                        chapter_text=chapter.raw_text,
                        book_id=book_id,
                        db=db,
                    )
                    await db.commit()
                    processed += 1
                    yield _sse(
                        "progress",
                        {
                            "chapter_number": ch_num,
                            "chapter_title": ch_title,
                            "status": "done",
                            "processed": processed,
                            "total": total,
                        },
                    )
                except Exception as exc:
                    await db.rollback()
                    failed_chapters.append(ch_num)
                    logger.error("第 %d 章角色卡构建失败：%s", ch_num, exc, exc_info=True)
                    yield _sse(
                        "chapter_error",
                        {
                            "chapter_number": ch_num,
                            "chapter_title": ch_title,
                            "error": str(exc),
                        },
                    )

                await asyncio.sleep(0)

            yield _sse(
                "complete",
                {
                    "processed": processed,
                    "total": total,
                    "failed_chapters": failed_chapters,
                    "message": (
                        "角色卡建立完成"
                        if not failed_chapters
                        else f"建立完成，{len(failed_chapters)} 章失败"
                    ),
                },
            )

        except Exception as exc:
            logger.error("书籍 %d 角色卡一键建立发生致命错误：%s", book_id, exc, exc_info=True)
            yield _sse("error", {"message": f"建立失败：{exc}"})
