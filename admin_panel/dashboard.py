"""
admin_panel/dashboard.py
~~~~~~~~~~~~~~~~~~~~~~~~
Advanced Admin Control Panel for InstaVault Bot.
This file handles the private admin dashboard UI and features.
"""

import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import config

logger = logging.getLogger(__name__)
router = Router(name="admin_panel")


# ===========================================================================
# FSM States
# ===========================================================================

class ApkUploadState(StatesGroup):
    """FSM states for the admin APK upload flow."""
    waiting_for_file = State()
    confirm_update = State()

def is_admin(user_id: int) -> bool:
    """Helper to check if a user is in the ADMIN_IDS list."""
    return user_id in config.ADMIN_IDS

@router.message(Command("admin"))
async def cmd_admin_panel(message: Message) -> None:
    """Command handler for /admin."""
    user_id = message.from_user.id if message.from_user else 0
    if not is_admin(user_id):
        await message.answer("⛔ <b>Access Denied.</b> You are not an Admin.")
        return

    from .keyboards import admin_dashboard_keyboard

    text = (
        "👑 <b>Advanced Admin Dashboard</b>\n\n"
        "Welcome to the control centre. Here you can manage the bot, "
        "check live statistics, and control user data.\n\n"
        "<i>(Note: Features are currently coming soon!)</i>"
    )

    await message.answer(text, reply_markup=admin_dashboard_keyboard())


@router.callback_query(F.data == "admin_dashboard")
async def cb_open_admin_dashboard(query: CallbackQuery) -> None:
    """Entry point for the Advanced Admin Panel via callback button."""
    if not query.message or not hasattr(query.message, 'edit_text'):
        await query.answer()
        return

    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.answer("⛔ Access Denied. You are not an Admin.", show_alert=True)
        return

    await query.answer()

    from .keyboards import admin_dashboard_keyboard

    text = (
        "👑 <b>Advanced Admin Dashboard</b>\n\n"
        "Welcome to the control centre. Here you can manage the bot, "
        "check live statistics, and control user data.\n\n"
        "<i>(Note: Features are currently coming soon!)</i>"
    )

    await query.message.edit_text(text, reply_markup=admin_dashboard_keyboard())

# ===========================================================================
# ADMIN FEATURE: Total Users Analytics
# ===========================================================================

@router.callback_query(F.data == "admin_users_count")
async def cb_admin_users_count(query: CallbackQuery) -> None:
    """
    Callback handler for '👥 Total Users Count' button.
    Fetches real-time count via Firestore Aggregation Query and updates UI.
    """
    if not query.message or not hasattr(query.message, 'edit_text'):
        await query.answer()
        return

    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.answer("⛔ Access Denied. You are not an Admin.", show_alert=True)
        return

    await query.answer()

    from database.db_manager import get_total_users_count
    from .keyboards import admin_back_keyboard

    try:
        # Fetch aggregation count asynchronously from DB
        total_users = await get_total_users_count()
        text = (
            "📊 <b>System Analytics — Users Count</b>\n\n"
            f"👥 <b>Total Registered Users:</b> <code>{total_users:,}</code>\n"
            "⚡ <b>Database Engine:</b> Firestore (Async Aggregated)\n"
            "🟢 <b>Status:</b> Active & Healthy"
        )
    except Exception as err:
        logger.error("Error rendering admin users count: %s", err)
        text = (
            "⚠️ <b>System Error</b>\n\n"
            "Failed to retrieve total user count from database."
        )

    await query.message.edit_text(text, reply_markup=admin_back_keyboard())


# ===========================================================================
# ADMIN FEATURE: Today New Accounts Analytics
# ===========================================================================

@router.callback_query(F.data == "admin_new_accounts_today")
async def cb_admin_new_accounts_today(query: CallbackQuery) -> None:
    """
    Callback handler for '🆕 New Accounts Today' button.
    Fetches real-time count of user accounts created today in IST.
    """
    if not query.message or not hasattr(query.message, 'edit_text'):
        await query.answer()
        return

    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.answer("⛔ Access Denied. You are not an Admin.", show_alert=True)
        return

    await query.answer()

    from database.db_manager import get_today_new_accounts_count
    from .keyboards import admin_back_keyboard

    try:
        count = await get_today_new_accounts_count()
        text = (
            "📅 <b>System Analytics — New Accounts Today</b>\n\n"
            f"🆕 <b>New Accounts Created Today (IST):</b> <code>{count:,} Users</code>\n"
            "🕒 <b>Calculation Window:</b> Since 12:00 AM IST\n"
            "⚡ <b>Primary Engine:</b> Redis Set / Firestore Aggregation\n"
            "🟢 <b>Status:</b> Active & Healthy"
        )
    except Exception as err:
        logger.error("Error rendering new accounts count today: %s", err)
        text = (
            "⚠️ <b>System Error</b>\n\n"
            "Failed to retrieve today's new accounts count."
        )

    await query.message.edit_text(text, reply_markup=admin_back_keyboard())


# ===========================================================================
# ADMIN FEATURE: Daily Active Users (DAU) Analytics
# ===========================================================================

@router.callback_query(F.data == "admin_dau_today")
async def cb_admin_dau_today(query: CallbackQuery) -> None:
    """
    Callback handler for '⚡ Today Active Users' button.
    Fetches real-time count of unique active users today from Redis (0 DB Cost).
    """
    if not query.message or not hasattr(query.message, 'edit_text'):
        await query.answer()
        return

    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.answer("⛔ Access Denied. You are not an Admin.", show_alert=True)
        return

    await query.answer()

    from database.redis_manager import get_today_active_users_count
    from .keyboards import admin_back_keyboard

    try:
        count = await get_today_active_users_count()
        text = (
            "⚡ <b>System Analytics — Daily Active Users (DAU)</b>\n\n"
            f"🔥 <b>Unique Active Users Today:</b> <code>{count:,} Users</code>\n"
            "📊 <b>Activity Scope:</b> Messages, Clicks, Orders & Starts\n"
            "⚡ <b>Primary Engine:</b> Redis Daily Set (0 DB Cost)\n"
            "🟢 <b>Status:</b> Active & Healthy"
        )
    except Exception as err:
        logger.error("Error rendering DAU count today: %s", err)
        text = (
            "⚠️ <b>System Error</b>\n\n"
            "Failed to retrieve DAU count from Redis."
        )

    await query.message.edit_text(text, reply_markup=admin_back_keyboard())


# ===========================================================================
# ADMIN FEATURE: Shortener Mission Analytics
# ===========================================================================

@router.callback_query(F.data == "admin_shortener_stats")
async def cb_admin_shortener_stats(query: CallbackQuery) -> None:
    """
    Callback handler for '📊 Shortener Stats' button.
    Fetches real-time analytics from Redis (0 Firestore reads).
    """
    if not query.message or not hasattr(query.message, 'edit_text'):
        await query.answer()
        return

    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.answer("⛔ Access Denied. You are not an Admin.", show_alert=True)
        return

    await query.answer()

    from database.redis_manager import get_shortener_stats
    from .keyboards import admin_back_keyboard

    try:
        stats = await get_shortener_stats()
        text = (
            "📊 <b>Shortener Mission Analytics</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "📅 <b>Aaj (IST):</b>\n"
            f"   ✅ Tasks Completed: <code>{stats['today_count']:,}</code>\n"
            f"   💰 Sparks Given: <code>{stats['today_sparks']:,}</code>\n\n"
            "📆 <b>All Time:</b>\n"
            f"   ✅ Total Tasks: <code>{stats['total_count']:,}</code>\n"
            f"   💰 Total Sparks: <code>{stats['total_sparks']:,}</code>\n"
            f"   👥 Unique Users: <code>{stats['unique_users']:,}</code>\n\n"
            "⚡ <b>Engine:</b> Redis Counters (0 DB Cost)\n"
            "🟢 <b>Status:</b> Active & Healthy"
        )
    except Exception as err:
        logger.error("Error rendering shortener stats: %s", err)
        text = (
            "⚠️ <b>System Error</b>\n\n"
            "Failed to retrieve shortener mission analytics."
        )

    await query.message.edit_text(text, reply_markup=admin_back_keyboard())


# ===========================================================================
# ADMIN FEATURE: APK Upload (FSM-Based)
# ===========================================================================
# Flow: Admin clicks "📱 Update APK" → Bot asks for file → Admin sends .apk
#       → Bot shows preview + [Confirm / Cancel] → Admin confirms → Saved.
# ===========================================================================

@router.callback_query(F.data == "admin_upload_apk")
async def cb_admin_upload_apk(query: CallbackQuery, state: FSMContext) -> None:
    """Entry point: Admin clicks '📱 Update APK' button in dashboard."""
    if not query.message or not hasattr(query.message, 'edit_text'):
        await query.answer()
        return

    if not is_admin(query.from_user.id):
        await query.answer("⛔ Access Denied. You are not an Admin.", show_alert=True)
        return

    await query.answer()

    from .keyboards import apk_upload_cancel_keyboard

    # Show current APK status + ask for file
    current_id = config.APK_FILE_ID
    status_line = (
        f"📎 Current File ID:\n<code>{current_id[:30]}...</code>"
        if current_id
        else "📎 Current File ID: <i>Not set</i>"
    )

    await query.message.edit_text(
        "📱 <b>APK Upload Manager</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{status_line}\n\n"
        "👇 <b>Naya APK file bhejiye.</b>\n"
        "Sirf <code>.apk</code> extension wali file accept hogi.\n\n"
        "<i>Cancel karne ke liye neeche button dabayein.</i>",
        reply_markup=apk_upload_cancel_keyboard(),
    )

    await state.set_state(ApkUploadState.waiting_for_file)
    logger.info("Admin %s entered APK upload mode.", query.from_user.id)


@router.message(ApkUploadState.waiting_for_file, F.document)
async def on_apk_file_received(message: Message, state: FSMContext) -> None:
    """Handle the file sent by admin while in APK upload FSM state."""
    if not is_admin(message.from_user.id):
        return

    doc = message.document

    # Validate: must be an .apk file
    file_name = doc.file_name or ""
    if not file_name.lower().endswith(".apk"):
        await message.reply(
            "⚠️ Sirf <code>.apk</code> file accept hoti hai.\n"
            "Kripya sahi file bhejiye ya Cancel karein.",
        )
        return

    # Store file details in FSM data for confirmation step
    file_size_mb = round((doc.file_size or 0) / (1024 * 1024), 2)
    await state.update_data(
        pending_file_id=doc.file_id,
        pending_file_name=file_name,
        pending_file_size_mb=file_size_mb,
    )

    from .keyboards import apk_upload_confirm_keyboard

    await message.answer(
        "📦 <b>APK File Received!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📄 <b>File:</b> <code>{file_name}</code>\n"
        f"📊 <b>Size:</b> {file_size_mb} MB\n\n"
        "Kya aap is APK ko live update karna chahte hain?\n"
        "Users ko ab yeh file milegi download button par.",
        reply_markup=apk_upload_confirm_keyboard(),
    )

    await state.set_state(ApkUploadState.confirm_update)
    logger.info(
        "Admin %s uploaded APK candidate: %s (%.2f MB)",
        message.from_user.id, file_name, file_size_mb,
    )


@router.message(ApkUploadState.waiting_for_file)
async def on_non_file_in_upload_state(message: Message) -> None:
    """Reject any non-document message while waiting for APK file."""
    if not is_admin(message.from_user.id):
        return

    await message.reply(
        "⚠️ Kripya ek <code>.apk</code> file bhejiye.\n"
        "Text, photo ya koi aur format accept nahi hoga.",
    )


@router.callback_query(F.data == "admin_apk_confirm", ApkUploadState.confirm_update)
async def cb_apk_confirm(query: CallbackQuery, state: FSMContext) -> None:
    """Admin confirmed the APK update — save to .env and update runtime."""
    if not query.message:
        await query.answer()
        return

    if not is_admin(query.from_user.id):
        await query.answer("⛔ Access Denied.", show_alert=True)
        return

    await query.answer()

    data = await state.get_data()
    file_id = data.get("pending_file_id", "")
    file_name = data.get("pending_file_name", "unknown")
    file_size_mb = data.get("pending_file_size_mb", 0)

    if not file_id:
        await query.message.edit_text(
            "⚠️ Session expired. Kripya dubara upload karein.",
        )
        await state.clear()
        return

    # Persist to .env and update runtime config
    from dotenv import set_key

    set_key(".env", "APK_FILE_ID", file_id)
    config.APK_FILE_ID = file_id

    await state.clear()

    from .keyboards import admin_back_keyboard

    await query.message.edit_text(
        "✅ <b>APK Updated Successfully!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📄 <b>File:</b> <code>{file_name}</code>\n"
        f"📊 <b>Size:</b> {file_size_mb} MB\n"
        f"🔑 <b>File ID:</b>\n<code>{file_id[:40]}...</code>\n\n"
        "Users ko ab download button par yeh file milegi. 🚀",
        reply_markup=admin_back_keyboard(),
    )

    logger.info(
        "APK updated by admin %s: %s (%.2f MB) → file_id=%s",
        query.from_user.id, file_name, file_size_mb, file_id[:30],
    )


@router.callback_query(F.data == "admin_apk_cancel")
async def cb_apk_cancel(query: CallbackQuery, state: FSMContext) -> None:
    """Cancel APK upload flow and return to admin dashboard."""
    if not query.message or not hasattr(query.message, 'edit_text'):
        await query.answer()
        return

    if not is_admin(query.from_user.id):
        await query.answer("⛔ Access Denied.", show_alert=True)
        return

    await query.answer("Upload cancelled.")
    await state.clear()

    from .keyboards import admin_dashboard_keyboard

    await query.message.edit_text(
        "👑 <b>Advanced Admin Dashboard</b>\n\n"
        "Welcome to the control centre. Here you can manage the bot, "
        "check live statistics, and control user data.\n\n"
        "<i>(Note: Features are currently coming soon!)</i>",
        reply_markup=admin_dashboard_keyboard(),
    )

    logger.info("Admin %s cancelled APK upload.", query.from_user.id)
