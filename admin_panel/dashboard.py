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

import config

logger = logging.getLogger(__name__)
router = Router(name="admin_panel")

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
