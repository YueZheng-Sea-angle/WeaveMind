from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.book import Book


class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    book_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chapter_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(500))
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, default=0)

    book: Mapped["Book"] = relationship("Book", back_populates="chapters")
    anchor: Mapped[Optional["ChapterAnchor"]] = relationship(
        "ChapterAnchor", back_populates="chapter", uselist=False, cascade="all, delete-orphan"
    )


class ChapterAnchor(Base):
    __tablename__ = "chapter_anchors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    chapter_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    summary: Mapped[Optional[str]] = mapped_column(Text)
    key_events: Mapped[list[Any]] = mapped_column(JSON, default=list)
    characters_present: Mapped[list[Any]] = mapped_column(JSON, default=list)
    foreshadowing: Mapped[list[Any]] = mapped_column(JSON, default=list)
    themes: Mapped[list[Any]] = mapped_column(JSON, default=list)

    chapter: Mapped["Chapter"] = relationship("Chapter", back_populates="anchor")
