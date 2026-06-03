from datetime import datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    pass


class CharacterCardCategory(str, PyEnum):
    """关键角色卡子条目的分类。"""

    BIOGRAPHY = "biography"          # 生平
    PERSONALITY = "personality"      # 性格特点
    RELATIONSHIP = "relationship"    # 人物关系
    SKILL = "skill"                  # 技能
    ITEM = "item"                    # 道具
    STATUS = "status"                # 当前状态
    FORESHADOWING = "foreshadowing"  # 关键伏笔


# 分类中文标签，供工具/Agent 输出时使用
CATEGORY_LABELS: dict[str, str] = {
    CharacterCardCategory.BIOGRAPHY.value: "生平",
    CharacterCardCategory.PERSONALITY.value: "性格特点",
    CharacterCardCategory.RELATIONSHIP.value: "人物关系",
    CharacterCardCategory.SKILL.value: "技能",
    CharacterCardCategory.ITEM.value: "道具",
    CharacterCardCategory.STATUS.value: "当前状态",
    CharacterCardCategory.FORESHADOWING.value: "关键伏笔",
}

VALID_CATEGORIES = {c.value for c in CharacterCardCategory}


class CharacterCard(Base):
    """关键角色卡：维护本书重点角色的结构化档案。

    与实体（Entity）平行但更细颗粒：每张卡片下挂多条按分类组织的子条目，
    卡片本身与每条子条目都带 enabled 状态，停用项不会作为上下文提供给对话大脑。
    """

    __tablename__ = "character_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    book_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 可选关联到已有实体（人物），删除实体时置空而非删除卡片
    entity_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("entities.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    # 卡片级启用开关：停用后整张卡片不进入对话上下文，对话大脑不可见
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    entries: Mapped[list["CharacterCardEntry"]] = relationship(
        "CharacterCardEntry",
        back_populates="card",
        cascade="all, delete-orphan",
        order_by="CharacterCardEntry.sort_order",
    )


class CharacterCardEntry(Base):
    """角色卡子条目：归属某张卡片、某个分类下的一条具体信息。"""

    __tablename__ = "character_card_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    card_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("character_cards.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text)
    # 条目级启用开关：默认启用，停用后不进入对话上下文，对话大脑不可见
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    card: Mapped["CharacterCard"] = relationship(
        "CharacterCard", back_populates="entries"
    )
