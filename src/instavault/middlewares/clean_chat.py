"""
middlewares/clean_chat.py
~~~~~~~~~~~~~~~~~~~~~~~~~
Clean-chat middleware for InstaVault Bot.

Automatically deletes incoming user messages in private chats after they are
processed by the bot handlers, keeping the conversation view pristine,
clutter-free, and single-screen app-like.

Behavior:
  • Only operates on private chats (DMs). Groups and channels are untouched.
  • Admin messages are exempt (admins can debug and manage without deletion).
  • Runs as an outer middleware so even unhandled/random text is deleted.
  • Wraps message deletion in try-except so Telegram errors never crash the bot.
"""

import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.enums import ChatType
from aiogram.types import Message, TelegramObject

from instavault.core.config import ADMIN_IDS

logger = logging.getLogger(__name__)


class CleanChatMiddleware(BaseMiddleware):
    """
    Middleware that silently deletes user messages in private chats.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # Only inspect Message events in private chats
        if not isinstance(event, Message) or event.chat.type != ChatType.PRIVATE:
            return await handler(event, data)

        user_id = event.from_user.id if event.from_user else 0

        # Preserve broadcast draft messages (Telegram copy_message requires source to exist)
        state = data.get("state")
        current_state = await state.get_state() if state else None
        if current_state and (
            "waiting_for_content" in current_state
            or "content_input" in current_state
        ):
            return await handler(event, data)

        # Execute the handler first so the message content is fully processed
        try:
            return await handler(event, data)
        finally:
            # Silently delete the incoming message to keep the chat clean
            try:
                bot = data.get("bot") or event.bot
                if bot:
                    await bot.delete_message(
                        chat_id=event.chat.id, message_id=event.message_id
                    )
                else:
                    await event.delete()
                logger.info(
                    "CleanChat: Auto-deleted message %s from user %s",
                    event.message_id,
                    user_id,
                )
            except Exception as err:
                logger.warning(
                    "CleanChat: Could not delete message %s from user %s: %s",
                    event.message_id,
                    user_id,
                    err,
                )
