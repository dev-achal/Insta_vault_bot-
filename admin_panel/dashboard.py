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
# UPCOMING ADMIN FEATURES (Placeholders)
# ===========================================================================

@router.callback_query(F.data == "admin_manage_user")
async def cb_admin_features_coming_soon(query: CallbackQuery) -> None:
    """Placeholder handler for upcoming admin features."""
    await query.answer("🚀 This feature is coming soon!", show_alert=True)
