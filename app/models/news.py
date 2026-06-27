"""ORM model for tracking processed tweets."""

from __future__ import annotations

import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ProcessedItem(Base):
    """Each row represents a news item that has been fetched, translated, and posted."""

    __tablename__ = "processed_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    item_id: Mapped[str] = mapped_column(
        String(512),
        unique=True,
        nullable=False,
        comment="Original RSS item GUID or link",
    )
    author_source: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="RSS feed source name",
    )
    original_title: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Raw news title",
    )
    translated_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="LLM-generated Russian summary",
    )
    image_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="URL of the attached media (if any)",
    )
    telegram_message_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Message ID returned by Telegram after posting",
    )
    processed_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_processed_items_item_id", "item_id"),
    )

    def __repr__(self) -> str:
        return f"<ProcessedItem item_id={self.item_id!r} source={self.author_source!r}>"
