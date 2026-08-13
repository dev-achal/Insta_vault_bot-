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
from datetime import datetime, timedelta
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
from utils.helpers import get_ist_now
from .keyboards import (
    broadcast_menu_keyboard,
    single_broadcast_confirm_keyboard,
    cron_time_presets_keyboard,
    cron_confirm_keyboard,
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


class CronBroadcastState(StatesGroup):
    select_time = State()
    custom_minutes_input = State()
    content_input = State()
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
async def cb_admin_broadcast_menu(query: CallbackQuery, state: FSMContext) -> None:
    """Entry callback handler for Broadcast Control Centre sub-menu."""
    if not query.message or not hasattr(query.message, "edit_text"):
        await query.answer()
        return

    if not is_admin(query.from_user.id):
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
# Cron Scheduled Broadcast Engine
# ===========================================================================

@router.callback_query(F.data == "broadcast_mode_cron")
async def cb_broadcast_mode_cron(query: CallbackQuery, state: FSMContext) -> None:
    """Start Scheduled Cron Broadcast setup flow."""
    if not query.message or not hasattr(query.message, "edit_text"):
        await query.answer()
        return

    if not is_admin(query.from_user.id):
        await query.answer("⛔ Access Denied.", show_alert=True)
        return

    await query.answer()
    await state.set_state(CronBroadcastState.select_time)

    text = (
        "⏰ <b>Scheduled Cron Broadcast Setup</b>\n\n"
        "Select when you would like this broadcast to automatically fire:\n\n"
        "• ⏱️ <b>In 10 Mins:</b> Fires in 10 minutes\n"
        "• ⏱️ <b>In 1 Hour:</b> Fires in 1 hour\n"
        "• ⏱️ <b>In 6 Hours:</b> Fires in 6 hours\n"
        "• ⏱️ <b>In 24 Hours:</b> Fires in 24 hours\n"
        "• ✏️ <b>Custom Minutes:</b> Specify custom delay in minutes"
    )

    await query.message.edit_text(text, reply_markup=cron_time_presets_keyboard())


@router.callback_query(CronBroadcastState.select_time, F.data.startswith("cron_time:"))
async def cb_cron_select_time(query: CallbackQuery, state: FSMContext) -> None:
    """Handle preset time selection for scheduled broadcast."""
    if not query.message or not hasattr(query.message, "edit_text"):
        await query.answer()
        return

    action = query.data.split(":")[1]

    if action == "cancel":
        await state.clear()
        await query.answer("Scheduled Broadcast cancelled.")
        await query.message.edit_text("❌ Scheduled Broadcast setup cancelled.", reply_markup=broadcast_menu_keyboard())
        return

    if action == "custom":
        await state.set_state(CronBroadcastState.custom_minutes_input)
        await query.answer()
        await query.message.edit_text(
            "✏️ <b>Custom Time Delay</b>\n\n"
            "Please send the delay duration in <b>Minutes</b> (e.g. <code>45</code> for 45 minutes, <code>120</code> for 2 hours):",
            reply_markup=admin_back_keyboard(),
        )
        return

    preset_map = {
        "10m": (600, "10 Minutes"),
        "1h": (3600, "1 Hour"),
        "6h": (21600, "6 Hours"),
        "24h": (86400, "24 Hours"),
    }

    if action not in preset_map:
        await query.answer("⚠️ Invalid selection.", show_alert=True)
        return

    delay_sec, delay_label = preset_map[action]
    fire_time = get_ist_now() + timedelta(seconds=delay_sec)
    fire_time_str = fire_time.strftime("%Y-%m-%d %I:%M:%S %p IST")

    await state.update_data(
        delay_seconds=delay_sec,
        delay_label=delay_label,
        fire_time_str=fire_time_str,
    )
    await state.set_state(CronBroadcastState.content_input)
    await query.answer()

    text = (
        "📝 <b>Scheduled Broadcast Content</b>\n\n"
        f"⏰ <b>Target Execution Time:</b> <code>{fire_time_str}</code> (Delay: {delay_label})\n\n"
        "Now send the broadcast message copy (Text, Photo, Video, or Formatting)."
    )

    await query.message.edit_text(text, reply_markup=admin_back_keyboard())


@router.message(CronBroadcastState.custom_minutes_input)
async def handle_cron_custom_minutes_input(message: Message, state: FSMContext) -> None:
    """Parse custom minutes input for scheduled broadcast."""
    if not message.from_user or not is_admin(message.from_user.id):
        return

    text = (message.text or "").strip()
    if not text.isdigit() or int(text) <= 0:
        await message.answer("⚠️ Invalid number of minutes. Please send a valid positive number (e.g. <code>30</code>):")
        return

    minutes = int(text)
    delay_sec = minutes * 60
    delay_label = f"{minutes} Minutes"
    fire_time = get_ist_now() + timedelta(seconds=delay_sec)
    fire_time_str = fire_time.strftime("%Y-%m-%d %I:%M:%S %p IST")

    await state.update_data(
        delay_seconds=delay_sec,
        delay_label=delay_label,
        fire_time_str=fire_time_str,
    )
    await state.set_state(CronBroadcastState.content_input)

    prompt = (
        "📝 <b>Scheduled Broadcast Content</b>\n\n"
        f"⏰ <b>Target Execution Time:</b> <code>{fire_time_str}</code> (Delay: {delay_label})\n\n"
        "Now send the broadcast message copy (Text, Photo, Video, or Formatting)."
    )

    await message.answer(prompt, reply_markup=admin_back_keyboard())


@router.message(CronBroadcastState.content_input)
async def handle_cron_broadcast_content(message: Message, state: FSMContext) -> None:
    """Store content and render confirmation screen for scheduled broadcast."""
    if not message.from_user or not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    fire_time_str = data.get("fire_time_str", "N/A")
    delay_label = data.get("delay_label", "N/A")

    await state.update_data(
        content_chat_id=message.chat.id,
        content_message_id=message.message_id,
    )
    await state.set_state(CronBroadcastState.confirm_send)

    confirm_text = (
        "⏰ <b>Scheduled Broadcast Preview</b>\n\n"
        f"🕒 <b>Scheduled Execution Time (IST):</b> <code>{fire_time_str}</code>\n"
        f"⏱️ <b>Time Delay:</b> <code>{delay_label}</code>\n"
        "👥 <b>Target Audience:</b> <b>All Registered Users</b>\n\n"
        "👇 <i>Copy Preview of the message is rendered below:</i>"
    )

    await message.answer(confirm_text, reply_markup=cron_confirm_keyboard())


@router.callback_query(CronBroadcastState.confirm_send, F.data == "cancel_cron_broadcast")
async def cb_cancel_cron_broadcast(query: CallbackQuery, state: FSMContext) -> None:
    """Cancel scheduled broadcast confirmation."""
    if not query.message or not hasattr(query.message, "edit_text"):
        await query.answer()
        return

    await state.clear()
    await query.answer("Scheduled Broadcast cancelled.")
    await query.message.edit_text("❌ Scheduled Broadcast setup cancelled.", reply_markup=broadcast_menu_keyboard())


@router.callback_query(CronBroadcastState.confirm_send, F.data == "confirm_cron_broadcast")
async def cb_confirm_cron_broadcast(query: CallbackQuery, state: FSMContext) -> None:
    """Schedule the background broadcast execution task."""
    if not query.message or not hasattr(query.message, "edit_text"):
        await query.answer()
        return

    admin_id = query.from_user.id
    if not is_admin(admin_id):
        await query.answer("⛔ Access Denied.", show_alert=True)
        return

    await query.answer()
    data = await state.get_data()
    await state.clear()

    delay_seconds = data.get("delay_seconds", 0)
    fire_time_str = data.get("fire_time_str", "N/A")
    delay_label = data.get("delay_label", "N/A")
    content_chat_id = data.get("content_chat_id")
    content_message_id = data.get("content_message_id")

    if not content_chat_id or not content_message_id:
        await query.message.edit_text("❌ Error: Broadcast payload lost. Please try again.")
        return

    # Launch non-blocking scheduled background task
    asyncio.create_task(
        run_scheduled_broadcast_task(
            bot=query.bot,
            admin_id=admin_id,
            content_chat_id=content_chat_id,
            content_message_id=content_message_id,
            delay_seconds=delay_seconds,
            fire_time_str=fire_time_str,
            delay_label=delay_label,
        )
    )

    success_msg = (
        "⏰ <b>BROADCAST SUCCESSFULLY SCHEDULED!</b>\n\n"
        f"🕒 <b>Scheduled Execution Time:</b> <code>{fire_time_str}</code>\n"
        f"⏱️ <b>Delay Duration:</b> <code>{delay_label}</code>\n"
        "👥 <b>Target Audience:</b> <b>All Registered Users</b>\n\n"
        "✅ The bot will automatically deliver this broadcast at the exact scheduled time and send a delivery report to your inbox."
    )

    await query.message.edit_text(success_msg, reply_markup=admin_back_keyboard())


async def run_scheduled_broadcast_task(
    bot: Any,
    admin_id: int,
    content_chat_id: int,
    content_message_id: int,
    delay_seconds: int,
    fire_time_str: str,
    delay_label: str,
) -> None:
    """Async background task that sleeps until the scheduled time and executes broadcast."""
    logger.info("⏰ Scheduled broadcast queued to fire in %d seconds (%s)", delay_seconds, fire_time_str)
    
    # Non-blocking sleep until target execution time
    await asyncio.sleep(max(0, delay_seconds))
    
    logger.info("⏰ Executing scheduled broadcast for admin %d...", admin_id)

    success_count = 0
    blocked_count = 0
    failed_count = 0
    total_processed = 0

    start_time = time.time()

    user_ids = await get_all_user_ids()
    for target_uid in user_ids:
        total_processed += 1
        delivered = False

        while not delivered:
            try:
                await bot.copy_message(
                    chat_id=target_uid,
                    from_chat_id=content_chat_id,
                    message_id=content_message_id,
                )
                success_count += 1
                delivered = True
            except TelegramRetryAfter as e:
                logger.warning("Rate limit hit during scheduled broadcast. Sleeping for %s seconds.", e.retry_after)
                await asyncio.sleep(e.retry_after + 1)
            except TelegramForbiddenError:
                blocked_count += 1
                delivered = True
            except (TelegramBadRequest, TelegramAPIError) as e:
                logger.error("Failed to deliver scheduled broadcast to %s: %s", target_uid, e)
                failed_count += 1
                delivered = True
            except Exception as e:
                logger.error("Unexpected error delivering scheduled broadcast to %s: %s", target_uid, e)
                failed_count += 1
                delivered = True

        # Rate limiting: 25 msgs/s
        await asyncio.sleep(0.04)

    duration = round(time.time() - start_time, 2)

    # Deliver final completion receipt to Admin
    report_text = (
        "⏰ <b>SCHEDULED BROADCAST EXECUTION COMPLETE</b>\n\n"
        f"🕒 <b>Scheduled Time:</b> <code>{fire_time_str}</code>\n"
        f"⏱️ <b>Total Duration:</b> <code>{duration}s</code>\n"
        f"📊 <b>Total Target Users:</b> <code>{total_processed:,}</code>\n\n"
        f"✅ <b>Successfully Delivered:</b> <code>{success_count:,}</code>\n"
        f"🚫 <b>Users Blocked Bot:</b> <code>{blocked_count:,}</code>\n"
        f"❌ <b>Delivery Failures:</b> <code>{failed_count:,}</code>"
    )

    try:
        await bot.send_message(admin_id, report_text)
    except Exception as err:
        logger.error("Failed to send scheduled broadcast completion report to admin %d: %s", admin_id, err)


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

    user_ids = await get_all_user_ids()
    for target_uid in user_ids:
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
