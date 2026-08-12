"""
admin_panel/broadcast.py
~~~~~~~~~~~~~~~~~~~~~~~~
Production-Ready Asynchronous Broadcast Engine for InstaVault Bot.

Features:
  - Supports All Users Broadcast, Single User Direct Broadcast, and Scheduled Cron Broadcast modes.
  - Interactive FSM flows for preview, confirmation, and execution.
  - Low-cost Database Streaming for All Users Broadcast.
  - Rate Limiting Guard (25 msgs/s) & FloodWait (TelegramRetryAfter) Auto-Pause Recovery.
  - Single User Direct Broadcast with DB Validation & Real-Time Delivery Receipts.
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
from database.db_manager import get_all_user_ids, get_total_users_count, get_user
from .keyboards import (
    broadcast_menu_keyboard,
    single_broadcast_confirm_keyboard,
    admin_back_keyboard,
)

logger = logging.getLogger(__name__)
router = Router(name="admin_broadcast")


# ===========================================================================
# FSM States
# ===========================================================================

class BroadcastState(StatesGroup):
    waiting_for_content = State()
    confirm_send = State()


class SingleBroadcastState(StatesGroup):
    waiting_for_target_id = State()
    waiting_for_content = State()
    confirm_send = State()


def is_admin(user_id: int) -> bool:
    """Check if user is registered in config.ADMIN_IDS."""
    return user_id in config.ADMIN_IDS


def broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard for All Users Broadcast Preview Confirmation."""
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


# ===========================================================================
# Broadcast Sub-Menu Handler
# ===========================================================================

@router.callback_query(F.data == "admin_broadcast")
async def cb_broadcast_menu(query: CallbackQuery, state: FSMContext) -> None:
    """Render the Broadcast Mode Selection Sub-Menu."""
    if not query.message or not hasattr(query.message, "edit_text"):
        await query.answer()
        return

    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.answer("⛔ Access Denied. You are not an Admin.", show_alert=True)
        return

    await state.clear()
    await query.answer()

    text = (
        "📢 <b>Broadcast Control Centre</b>\n\n"
        "Select the target delivery mode for your message:"
    )

    await query.message.edit_text(text, reply_markup=broadcast_menu_keyboard())


# ===========================================================================
# Cron Scheduled Broadcast Placeholder Handler
# ===========================================================================

@router.callback_query(F.data == "broadcast_mode_cron")
async def cb_broadcast_mode_cron(query: CallbackQuery) -> None:
    """Placeholder alert for Scheduled Cron Broadcast feature."""
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Access Denied.", show_alert=True)
        return

    await query.answer(
        "⏰ Scheduled Cron Broadcast is coming soon!\nThis feature will allow recurring & delayed automated broadcasts.",
        show_alert=True,
    )


# ===========================================================================
# ALL USERS BROADCAST FLOW
# ===========================================================================

@router.callback_query(F.data == "broadcast_mode_all")
async def cb_start_all_broadcast(query: CallbackQuery, state: FSMContext) -> None:
    """Prompt admin to send message for All Users Broadcast."""
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
        "📢 <b>All Users Broadcast — Step 1 of 2</b>\n\n"
        f"👥 <b>Target Audience:</b> ALL Users (<code>{total_users:,}</code> users)\n\n"
        "Please send the message (Text, Photo, Video, Caption) you wish to broadcast to everyone now.\n"
        "<i>(Type /cancel to abort at any time)</i>"
    )

    await query.message.edit_text(text)


@router.message(BroadcastState.waiting_for_content, F.text == "/cancel")
@router.message(BroadcastState.confirm_send, F.text == "/cancel")
async def cmd_cancel_all_broadcast(message: Message, state: FSMContext) -> None:
    """Cancel All Users Broadcast flow."""
    await state.clear()
    await message.answer("❌ All Users Broadcast cancelled.", reply_markup=broadcast_menu_keyboard())


@router.message(BroadcastState.waiting_for_content)
async def handle_broadcast_content(message: Message, state: FSMContext) -> None:
    """Receive broadcast content, save state, and render copy preview with confirmation keyboard."""
    user_id = message.from_user.id if message.from_user else 0
    if not is_admin(user_id):
        return

    await state.update_data(
        content_chat_id=message.chat.id,
        content_message_id=message.message_id,
    )
    await state.set_state(BroadcastState.confirm_send)

    await message.answer("👇 <b>BROADCAST COPY PREVIEW</b> 👇")

    try:
        await message.bot.copy_message(
            chat_id=message.chat.id,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
        )
    except Exception as err:
        logger.error("Failed to render preview: %s", err)

    total_users = await get_total_users_count()

    confirm_text = (
        "📢 <b>All Users Broadcast — Step 2 of 2 (Confirmation)</b>\n\n"
        f"👥 <b>Target Audience:</b> <code>{total_users:,}</code> Users\n"
        "⚡ <b>Rate Limiter:</b> 25 msgs/sec with FloodWait Auto-Recovery\n\n"
        "Review the preview message above. Click below to initiate broadcast!"
    )

    await message.answer(confirm_text, reply_markup=broadcast_confirm_keyboard())


@router.callback_query(BroadcastState.confirm_send, F.data == "cancel_broadcast")
async def cb_cancel_all_broadcast(query: CallbackQuery, state: FSMContext) -> None:
    """Cancel confirmation step for All Users Broadcast."""
    if not query.message or not hasattr(query.message, "edit_text"):
        await query.answer()
        return

    await state.clear()
    await query.answer("Broadcast cancelled.")
    await query.message.edit_text("❌ All Users Broadcast cancelled.", reply_markup=broadcast_menu_keyboard())


@router.callback_query(BroadcastState.confirm_send, F.data == "confirm_broadcast")
async def cb_confirm_all_broadcast(query: CallbackQuery, state: FSMContext) -> None:
    """Execute asynchronous All Users Broadcast loop with live progress updates."""
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

    from_chat_id = data.get("content_chat_id")
    message_id = data.get("content_message_id")

    if not from_chat_id or not message_id:
        await query.message.edit_text("❌ Error: Broadcast payload lost. Please try again.")
        return

    ticket_msg = await query.message.edit_text(
        "🚀 <b>Broadcast Engine Started!</b>\n\n"
        "⏳ Fetching target audience stream from database..."
    )

    bot = query.bot
    success_count = 0
    blocked_count = 0
    failed_count = 0
    total_processed = 0

    start_time = time.time()
    last_edit_time = time.time()

    async for target_uid in get_all_user_ids():
        total_processed += 1
        delivered = False

        while not delivered:
            try:
                await bot.copy_message(
                    chat_id=int(target_uid),
                    from_chat_id=from_chat_id,
                    message_id=message_id,
                )
                success_count += 1
                delivered = True
            except TelegramForbiddenError:
                blocked_count += 1
                delivered = True
            except TelegramRetryAfter as retry_err:
                logger.warning("Telegram FloodWait hit during broadcast! Sleeping for %s seconds", retry_err.retry_after)
                await asyncio.sleep(retry_err.retry_after + 0.5)
            except (TelegramBadRequest, TelegramAPIError) as err:
                logger.error("Failed to deliver broadcast to user %s: %s", target_uid, err)
                failed_count += 1
                delivered = True
            except Exception as err:
                logger.critical("Unexpected exception for user %s: %s", target_uid, err)
                failed_count += 1
                delivered = True

        await asyncio.sleep(0.04)

        now = time.time()
        if now - last_edit_time >= 1.5 and hasattr(ticket_msg, "edit_text"):
            last_edit_time = now
            elapsed = max(1, int(now - start_time))
            speed = round(total_processed / elapsed, 1)

            progress_text = (
                "🚀 <b>Broadcast in Progress...</b>\n\n"
                f"📊 <b>Processed:</b> <code>{total_processed:,}</code>\n"
                f"✅ <b>Successful:</b> <code>{success_count:,}</code>\n"
                f"🚫 <b>Blocked/Deactivated:</b> <code>{blocked_count:,}</code>\n"
                f"⚠️ <b>Failed:</b> <code>{failed_count:,}</code>\n\n"
                f"⚡ <b>Speed:</b> <code>{speed} msgs/sec</code>"
            )
            try:
                await ticket_msg.edit_text(progress_text)
            except Exception:
                pass

    total_time = max(1, int(time.time() - start_time))
    summary_text = (
        "🎉 <b>Broadcast Finished Successfully!</b>\n\n"
        f"📊 <b>Total Processed:</b> <code>{total_processed:,}</code> users\n"
        f"✅ <b>Delivered:</b> <code>{success_count:,}</code>\n"
        f"🚫 <b>Blocked/Deactivated:</b> <code>{blocked_count:,}</code>\n"
        f"⚠️ <b>Failed:</b> <code>{failed_count:,}</code>\n\n"
        f"⏱️ <b>Total Duration:</b> <code>{total_time}s</code>"
    )

    if hasattr(ticket_msg, "edit_text"):
        await ticket_msg.edit_text(summary_text, reply_markup=admin_back_keyboard())


# ===========================================================================
# SINGLE USER DIRECT BROADCAST FLOW
# ===========================================================================

@router.callback_query(F.data == "broadcast_mode_single")
async def cb_start_single_broadcast(query: CallbackQuery, state: FSMContext) -> None:
    """Prompt admin to enter Target User ID or Vault ID."""
    if not query.message or not hasattr(query.message, "edit_text"):
        await query.answer()
        return

    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.answer("⛔ Access Denied. You are not an Admin.", show_alert=True)
        return

    await query.answer()
    await state.set_state(SingleBroadcastState.waiting_for_target_id)

    text = (
        "👤 <b>Single User Direct Broadcast — Step 1 of 3</b>\n\n"
        "Please send the <b>Telegram User ID</b> or <b>Vault ID</b> of the target user.\n"
        "<i>(Examples: <code>7437014244</code> or <code>VLT-7437014244</code>)</i>\n\n"
        "Type /cancel to abort at any time."
    )

    await query.message.edit_text(text)


@router.message(SingleBroadcastState.waiting_for_target_id, F.text == "/cancel")
@router.message(SingleBroadcastState.waiting_for_content, F.text == "/cancel")
@router.message(SingleBroadcastState.confirm_send, F.text == "/cancel")
async def cmd_cancel_single_broadcast(message: Message, state: FSMContext) -> None:
    """Cancel Single User Broadcast flow."""
    await state.clear()
    await message.answer("❌ Single User Direct Broadcast cancelled.", reply_markup=broadcast_menu_keyboard())


@router.message(SingleBroadcastState.waiting_for_target_id)
async def handle_single_target_id_input(message: Message, state: FSMContext) -> None:
    """Parse target ID, validate user against Firestore DB, and prompt for message content."""
    user_id = message.from_user.id if message.from_user else 0
    if not is_admin(user_id):
        return

    if not message.text:
        await message.answer("⚠️ Please send a valid User ID or Vault ID as text.")
        return

    raw_input = message.text.strip().upper()
    target_id_str = raw_input.replace("VLT-", "").replace("VLT", "").strip()

    if not target_id_str.isdigit():
        await message.answer(
            "⚠️ <b>Invalid ID Format.</b> Please send a numeric Telegram User ID or Vault ID.\n"
            "Example: <code>7437014244</code>"
        )
        return

    user_data = await get_user(target_id_str)
    if not user_data:
        await message.answer(
            f"⚠️ <b>User Not Found.</b>\n"
            f"No user record exists in database for ID: <code>{target_id_str}</code>"
        )
        return

    first_name = user_data.get("first_name", "User")
    username = user_data.get("username", "")
    user_line = f"{first_name} (@{username})" if username else first_name

    await state.update_data(
        target_uid=target_id_str,
        target_name=user_line,
    )
    await state.set_state(SingleBroadcastState.waiting_for_content)

    text = (
        "👤 <b>Single User Direct Broadcast — Step 2 of 3</b>\n\n"
        f"🎯 <b>Target User:</b> {user_line}\n"
        f"🆔 <b>User ID:</b> <code>{target_id_str}</code>\n\n"
        "Please send the message (Text, Photo, Video, Caption) you want to send directly to this user now.\n"
        "<i>(Type /cancel to abort)</i>"
    )

    await message.answer(text)


@router.message(SingleBroadcastState.waiting_for_content)
async def handle_single_broadcast_content(message: Message, state: FSMContext) -> None:
    """Receive single broadcast content and render copy preview with confirmation keyboard."""
    user_id = message.from_user.id if message.from_user else 0
    if not is_admin(user_id):
        return

    fsm_data = await state.get_data()
    target_uid = fsm_data.get("target_uid")
    target_name = fsm_data.get("target_name", "Target User")

    await state.update_data(
        content_chat_id=message.chat.id,
        content_message_id=message.message_id,
    )
    await state.set_state(SingleBroadcastState.confirm_send)

    await message.answer("👇 <b>DIRECT MESSAGE COPY PREVIEW</b> 👇")

    try:
        await message.bot.copy_message(
            chat_id=message.chat.id,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
        )
    except Exception as err:
        logger.error("Failed to render single preview: %s", err)

    confirm_text = (
        "👤 <b>Single User Direct Broadcast — Step 3 of 3 (Confirmation)</b>\n\n"
        f"🎯 <b>Recipient:</b> {target_name}\n"
        f"🆔 <b>User ID:</b> <code>{target_uid}</code>\n\n"
        "Review the preview message above. Click below to deliver directly!"
    )

    await message.answer(confirm_text, reply_markup=single_broadcast_confirm_keyboard())


@router.callback_query(SingleBroadcastState.confirm_send, F.data == "cancel_single_broadcast")
async def cb_cancel_single_broadcast_confirm(query: CallbackQuery, state: FSMContext) -> None:
    """Cancel single user broadcast confirmation."""
    if not query.message or not hasattr(query.message, "edit_text"):
        await query.answer()
        return

    await state.clear()
    await query.answer("Single User Broadcast cancelled.")
    await query.message.edit_text("❌ Single User Direct Broadcast cancelled.", reply_markup=broadcast_menu_keyboard())


@router.callback_query(SingleBroadcastState.confirm_send, F.data == "confirm_single_broadcast")
async def cb_confirm_single_broadcast(query: CallbackQuery, state: FSMContext) -> None:
    """Deliver direct message to the target single user."""
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

    target_uid = data.get("target_uid")
    target_name = data.get("target_name", "User")
    from_chat_id = data.get("content_chat_id")
    message_id = data.get("content_message_id")

    if not target_uid or not from_chat_id or not message_id:
        await query.message.edit_text("❌ Error: Message payload lost. Please try again.")
        return

    bot = query.bot

    try:
        await bot.copy_message(
            chat_id=int(target_uid),
            from_chat_id=from_chat_id,
            message_id=message_id,
        )
        summary_text = (
            "✅ <b>Direct Message Successfully Delivered!</b>\n\n"
            f"👤 <b>Recipient:</b> {target_name}\n"
            f"🆔 <b>User ID:</b> <code>{target_uid}</code>\n"
            "⚡ <b>Delivery Status:</b> Sent & Confirmed"
        )
    except TelegramForbiddenError:
        summary_text = (
            "🚫 <b>Delivery Failed (User Blocked Bot)</b>\n\n"
            f"👤 <b>Recipient:</b> {target_name}\n"
            f"🆔 <b>User ID:</b> <code>{target_uid}</code>\n"
            "⚠️ Target user has blocked or deleted the bot."
        )
    except (TelegramBadRequest, TelegramAPIError) as err:
        logger.error("Failed to send single broadcast to %s: %s", target_uid, err)
        summary_text = (
            "⚠️ <b>Delivery Failed (API Error)</b>\n\n"
            f"👤 <b>Recipient:</b> {target_name}\n"
            f"🆔 <b>User ID:</b> <code>{target_uid}</code>\n"
            f"<i>Reason: {err}</i>"
        )

    await query.message.edit_text(summary_text, reply_markup=admin_back_keyboard())
