from enum import Enum as PyEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.book import Book
    from app.models.chapter import Chapter


class EntityType(str, PyEnum):
    CHARACTER = "character"
    ORGANIZATION = "organization"
    LOCATION = "location"
    OBJECT = "object"
    CONCEPT = "concept"


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    book_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    type: Mapped[str] = mapped_column(String(50), default=EntityType.CHARACTER)
    description: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    first_appearance_chapter: Mapped[int | None] = mapped_column(Integer)

    book: Mapped["Book"] = relationship("Book", back_populates="entities")
    source_relations: Mapped[list["Relation"]] = relationship(
        "Relation", foreign_keys="Relation.source_id", back_populates="source"
    )
    target_relations: Mapped[list["Relation"]] = relationship(
        "Relation", foreign_keys="Relation.target_id", back_populates="target"
    )


class Relation(Base):
    __tablename__ = "relations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    book_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    target_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    relation_type: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    chapter_range: Mapped[list[int]] = mapped_column(JSON, default=list)

    book: Mapped["Book"] = relationship("Book", back_populates="relations")
    source: Mapped["Entity"] = relationship(
        "Entity", foreign_keys=[source_id], back_populates="source_relations"
    )
    target: Mapped["Entity"] = relationship(
        "Entity", foreign_keys=[target_id], back_populates="target_relations"
    )


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    book_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chapter_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("chapters.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    involved_entities: Mapped[list[Any]] = mapped_column(JSON, default=list)
    story_timestamp: Mapped[str | None] = mapped_column(String(200))

    book: Mapped["Book"] = relationship("Book", back_populates="events")
    chapter: Mapped["Chapter | None"] = relationship("Chapter")
