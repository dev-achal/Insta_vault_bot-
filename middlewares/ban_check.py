"""
middlewares/ban_check.py
~~~~~~~~~~~~~~~~~~~~~~~~
High-performance In-Memory Ban Check Middleware.
Protects bot from banned users without incurring database reads on every request.
"""

import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict, Set

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

import config
from database.db_manager import get_banned_user_ids

logger = logging.getLogger(__name__)

# Global in-memory set for 0-database-cost ban checking
BANNED_USER_CACHE: Set[str] = set()


async def init_ban_cache() -> None:
    """Initialize the in-memory ban cache from Firestore on startup."""
    global BANNED_USER_CACHE
    try:
        BANNED_USER_CACHE = await get_banned_user_ids()
        logger.info("✅ Banned user cache initialized with %d banned users.", len(BANNED_USER_CACHE))
    except Exception as e:
        logger.error("Failed to initialize ban cache: %s", e)


def add_to_ban_cache(user_id: int | str) -> None:
    """Add a user ID to the in-memory ban cache."""
    BANNED_USER_CACHE.add(str(user_id))


def remove_from_ban_cache(user_id: int | str) -> None:
    """Remove a user ID from the in-memory ban cache."""
    BANNED_USER_CACHE.discard(str(user_id))


def is_user_banned(user_id: int | str) -> bool:
    """Check if a user is in the in-memory ban cache."""
    return str(user_id) in BANNED_USER_CACHE


class BanCheckMiddleware(BaseMiddleware):
    """
    Middleware to intercept incoming updates and block banned users instantly.
    Zero-cost database check using in-memory set.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user:
            user_id = user.id
            # Admins are never blocked by ban middleware
            if user_id not in config.ADMIN_IDS and str(user_id) in BANNED_USER_CACHE:
                text = (
                    "🚫 <b>Your Account Has Been Suspended.</b>\n\n"
                    "You are restricted from using InstaVault Bot due to a policy violation.\n"
                    "If you believe this is a mistake, please contact support."
                )
                if isinstance(event, Message):
                    await event.answer(text)
                elif isinstance(event, CallbackQuery):
                    await event.answer("🚫 Account Suspended", show_alert=True)
                    if event.message and hasattr(event.message, "edit_text"):
                        await event.message.edit_text(text)
                return  # Terminate processing immediately

            # Concurrently record DAU activity in Redis without delaying request processing
            from database.redis_manager import record_user_activity
            asyncio.create_task(record_user_activity(user_id))

        return await handler(event, data)
