"""
admin_panel/broadcast.py
~~~~~~~~~~~~~~~~~~~~~~~~
Production-Ready Asynchronous Broadcast Engine for InstaVault Bot.

Features:
  - Supports Text, Photo, Video, Caption, and formatted content via Telegram's copy_message.
  - Interactive FSM flow: Prompt -> Preview -> Confirmation -> Live Progress -> Summary.
  - Low-cost Database Streaming: Uses Firestore select([]) field projection.
  - Rate Limiting Guard: Max 25 messages/sec (asyncio.sleep(0.04)) to protect against Telegram limits.
  - Non-blocking Exception Shield: Gracefully handles BotBlocked / UserDeactivated / TelegramAPIError.
"""

import asyncio
import logging
import time
from typing import Any

from aiogram import F, Router
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import config
from database.db_manager import get_all_user_ids, get_total_users_count

logger = logging.getLogger(__name__)
router = Router(name="admin_broadcast")


# ===========================================================================
# FSM States & Keyboards
# ===========================================================================

class BroadcastState(StatesGroup):
    waiting_for_content = State()
    confirm_send = State()


def is_admin(user_id: int) -> bool:
    """Check if user is registered in config.ADMIN_IDS."""
    return user_id in config.ADMIN_IDS


def broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard for Broadcast Preview Confirmation."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🚀 Confirm & Broadcast Now", callback_data="confirm_broadcast"),
            ],
            [
                InlineKeyboardButton(text="❌ Cancel Broadcast", callback_data="cancel_broadcast"),
            ],
        ]
    )


def broadcast_back_keyboard() -> InlineKeyboardMarkup:
    """Back button after broadcast summary."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔙 Back to Admin Panel", callback_data="admin_dashboard")
            ]
        ]
    )


# ===========================================================================
# Step 1: Initiate Broadcast Flow
# ===========================================================================

@router.callback_query(F.data == "admin_broadcast")
async def cb_start_broadcast(query: CallbackQuery, state: FSMContext) -> None:
    """Prompt the admin to send the message for broadcast."""
    if not query.message or not hasattr(query.message, "edit_text"):
        await query.answer()
        return

    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.answer("⛔ Access Denied. You are not an Admin.", show_alert=True)
        return

    await query.answer()
    await state.set_state(BroadcastState.waiting_for_content)

    total_users = await get_total_users_count()

    text = (
        "📢 <b>Broadcast Engine — Step 1 of 2</b>\n\n"
        f"👥 <b>Total Target Audience:</b> <code>{total_users:,}</code> users\n\n"
        "Please send the message you wish to broadcast now.\n"
        "<i>(Supports Text, Photos, Videos, Captions, and Formatted Posts)</i>\n\n"
        "Type /cancel to abort at any time."
    )

    await query.message.edit_text(text)


# ===========================================================================
# Step 2: Receive Message & Render Preview
# ===========================================================================

@router.message(BroadcastState.waiting_for_content, F.text == "/cancel")
async def cmd_cancel_broadcast(message: Message, state: FSMContext) -> None:
    """Cancel the broadcast flow."""
    await state.clear()
    from .keyboards import admin_dashboard_keyboard
    await message.answer("❌ Broadcast flow cancelled.", reply_markup=admin_dashboard_keyboard())


@router.message(BroadcastState.waiting_for_content)
async def handle_broadcast_content(message: Message, state: FSMContext) -> None:
    """Receive broadcast content, save state, and display preview."""
    user_id = message.from_user.id if message.from_user else 0
    if not is_admin(user_id):
        return

    # Store origin message details for copying
    await state.update_data(
        chat_id=message.chat.id,
        message_id=message.message_id,
    )
    await state.set_state(BroadcastState.confirm_send)

    await message.answer("👇 <b>BROADCAST PREVIEW</b> 👇")

    # Send exact copy to admin as a preview
    try:
        await message.copy_to(chat_id=message.chat.id)
    except Exception as err:
        logger.error("Failed to render broadcast preview: %s", err)

    await message.answer(
        "⬆️ <b>Above is your Broadcast Preview.</b>\n\n"
        "Are you sure you want to send this to all users?",
        reply_markup=broadcast_confirm_keyboard(),
    )


# ===========================================================================
# Step 3: Cancel Broadcast Callback
# ===========================================================================

@router.callback_query(BroadcastState.confirm_send, F.data == "cancel_broadcast")
async def cb_cancel_broadcast(query: CallbackQuery, state: FSMContext) -> None:
    """Handle broadcast cancellation from preview screen."""
    await state.clear()
    await query.answer("Broadcast Cancelled")
    if query.message and hasattr(query.message, "edit_text"):
        from .keyboards import admin_dashboard_keyboard
        await query.message.edit_text("❌ Broadcast cancelled.", reply_markup=admin_dashboard_keyboard())


# ===========================================================================
# Step 4: Confirm & Execute Asynchronous Broadcast Engine
# ===========================================================================

@router.callback_query(BroadcastState.confirm_send, F.data == "confirm_broadcast")
async def cb_confirm_broadcast(query: CallbackQuery, state: FSMContext) -> None:
    """
    Execute the asynchronous rate-limited broadcast to all user IDs.
    Includes TelegramRetryAfter (FloodWait) auto-pause and Time-Based UI updates.
    """
    if not query.message or not hasattr(query.message, "edit_text"):
        await query.answer()
        return

    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.answer("⛔ Access Denied.", show_alert=True)
        return

    await query.answer()

    data = await state.get_data()
    await state.clear()

    origin_chat_id = data.get("chat_id")
    origin_msg_id = data.get("message_id")

    if not origin_chat_id or not origin_msg_id:
        await query.message.edit_text("⚠️ Invalid broadcast state. Please try again.")
        return

    # Stream user IDs using Firestore field projection (low network/read cost)
    user_ids = await get_all_user_ids()
    total_targets = len(user_ids)

    if total_targets == 0:
        await query.message.edit_text("⚠️ No registered users found for broadcast.")
        return

    progress_msg = await query.message.edit_text(
        f"⏳ <b>Broadcast Engine Started...</b>\n\n"
        f"👥 Total Targets: <b>{total_targets:,}</b>\n"
        f"🟢 Delivered: <b>0</b>\n"
        f"🚫 Blocked/Failed: <b>0</b>"
    )

    sent_count = 0
    failed_count = 0
    start_time = time.time()
    last_edit_time = start_time
    bot = query.bot

    # Asynchronous broadcast loop with rate-limiting, FloodWait retry, and exception shielding
    for idx, target_uid_str in enumerate(user_ids, start=1):
        delivered = False
        while not delivered:
            try:
                target_uid = int(target_uid_str)
                await bot.copy_message(
                    chat_id=target_uid,
                    from_chat_id=origin_chat_id,
                    message_id=origin_msg_id,
                )
                sent_count += 1
                delivered = True
            except TelegramRetryAfter as retry_err:
                # Catch 429 FloodWait error: Auto-pause and retry same user without marking as failure
                wait_seconds = retry_err.retry_after
                logger.warning("Telegram FloodWait hit for user %s. Pausing for %s seconds", target_uid_str, wait_seconds)
                await asyncio.sleep(wait_seconds)
            except (TelegramForbiddenError, TelegramBadRequest):
                # User blocked the bot or account deactivated
                failed_count += 1
                delivered = True
            except TelegramAPIError as api_err:
                logger.warning("Telegram API error for user %s: %s", target_uid_str, api_err)
                failed_count += 1
                delivered = True
            except Exception as unk_err:
                logger.error("Unexpected error broadcasting to %s: %s", target_uid_str, unk_err)
                failed_count += 1
                delivered = True

        # Rate Limiting: Sleep 0.04s => ~25 messages/second (Safe Telegram API limit)
        await asyncio.sleep(0.04)

        # TIME-BASED UI THROTTLING: Update live progress ticket at most once every 1.5s (or at final target)
        now = time.time()
        if (now - last_edit_time >= 1.5) or (idx == total_targets):
            try:
                await progress_msg.edit_text(
                    f"⏳ <b>Broadcasting in Progress...</b>\n\n"
                    f"👥 Progress: <b>{idx:,} / {total_targets:,}</b>\n"
                    f"🟢 Delivered: <b>{sent_count:,}</b>\n"
                    f"🚫 Blocked/Failed: <b>{failed_count:,}</b>"
                )
                last_edit_time = now
            except TelegramRetryAfter as edit_retry:
                await asyncio.sleep(edit_retry.retry_after)
            except Exception:
                pass

    elapsed_time = round(time.time() - start_time, 2)

    # Final summary report ticket
    summary_text = (
        "✅ <b>Broadcast Completed Successfully!</b>\n\n"
        f"👥 <b>Total Audience:</b> <code>{total_targets:,}</code>\n"
        f"🟢 <b>Successfully Delivered:</b> <code>{sent_count:,}</code>\n"
        f"🚫 <b>Blocked / Failed:</b> <code>{failed_count:,}</code>\n"
        f"⏱️ <b>Duration:</b> <code>{elapsed_time}s</code>"
    )

    try:
        await progress_msg.edit_text(summary_text, reply_markup=broadcast_back_keyboard())
    except Exception:
        await query.message.answer(summary_text, reply_markup=broadcast_back_keyboard())
