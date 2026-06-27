"""Telegram posting service using aiogram v3."""

from __future__ import annotations

import io
import logging

import httpx
from aiogram import Bot
from aiogram.enums import ParseMode

from app.core.config import settings

logger = logging.getLogger(__name__)

_bot: Bot | None = None


def _get_bot() -> Bot:
    """Lazily initialise the aiogram Bot instance."""
    global _bot  # noqa: PLW0603
    if _bot is None:
        _bot = Bot(
            token=settings.TELEGRAM_BOT_TOKEN,
            default=None,
        )
    return _bot


async def post_to_channel(
    text: str,
    image_url: str | None = None,
) -> int | None:
    """Post a message (optionally with a photo) to the configured Telegram channel.

    Parameters
    ----------
    text:
        The formatted message text (Markdown).
    image_url:
        Optional URL of an image to attach.

    Returns
    -------
    int | None
        The Telegram ``message_id`` on success, or ``None`` on failure.
    """
    bot = _get_bot()
    channel = settings.TELEGRAM_CHANNEL_ID

    try:
        if image_url:
            image_bytes = None
            try:
                # Use a real browser user agent to avoid 503s from CDNs
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                async with httpx.AsyncClient(timeout=20, headers=headers) as client:
                    img_resp = await client.get(image_url)
                    img_resp.raise_for_status()
                    image_bytes = img_resp.content
            except Exception as e:
                logger.warning("Failed to download image %s, falling back to text-only: %s", image_url, e)

            if image_bytes:
                from aiogram.types import BufferedInputFile
                photo = BufferedInputFile(
                    file=image_bytes,
                    filename="news_image.jpg",
                )
                msg = await bot.send_photo(
                    chat_id=channel,
                    photo=photo,
                    caption=text,
                    parse_mode=ParseMode.MARKDOWN,
                )
            else:
                msg = await bot.send_message(
                    chat_id=channel,
                    text=text,
                    parse_mode=ParseMode.MARKDOWN,
                )
        else:
            msg = await bot.send_message(
                chat_id=channel,
                text=text,
                parse_mode=ParseMode.MARKDOWN,
            )

        logger.info("Posted to Telegram channel %s — message_id=%d", channel, msg.message_id)
        return msg.message_id

    except Exception:
        logger.exception("Failed to post to Telegram channel %s.", channel)
        return None


async def close_bot() -> None:
    """Gracefully close the bot session."""
    global _bot  # noqa: PLW0603
    if _bot is not None:
        await _bot.session.close()
        _bot = None
