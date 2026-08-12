"""
admin_panel/manage_user.py
~~~~~~~~~~~~~~~~~~~~~~~~~~
Admin User Management Panel (Search, Profile View, Ban/Unban Engine).
Allows admins to lookup users by Telegram ID or Vault ID, view stats, and toggle ban status.
"""

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import config
from database.db_manager import ban_user, get_user, unban_user
from middlewares.ban_check import add_to_ban_cache, is_user_banned, remove_from_ban_cache

logger = logging.getLogger(__name__)
router = Router(name="admin_manage_user")


# ===========================================================================
# FSM States & Keyboards
# ===========================================================================

class ManageUserState(StatesGroup):
    waiting_for_user_id = State()


def is_admin(user_id: int) -> bool:
    """Check if user is registered in config.ADMIN_IDS."""
    return user_id in config.ADMIN_IDS


def user_manage_keyboard(target_id: str, is_banned: bool) -> InlineKeyboardMarkup:
    """Inline keyboard for User Profile Management."""
    action_button = (
        InlineKeyboardButton(text="✅ Unban User", callback_data=f"admin_unban_user:{target_id}")
        if is_banned
        else InlineKeyboardButton(text="🚫 Ban User", callback_data=f"admin_ban_user:{target_id}")
    )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [action_button],
            [
                InlineKeyboardButton(text="🔙 Back to Admin Panel", callback_data="admin_dashboard")
            ],
        ]
    )


# ===========================================================================
# Step 1: Initiate User Lookup Flow
# ===========================================================================

@router.callback_query(F.data == "admin_manage_user")
async def cb_start_manage_user(query: CallbackQuery, state: FSMContext) -> None:
    """Prompt admin to enter User ID or Vault ID."""
    if not query.message or not hasattr(query.message, "edit_text"):
        await query.answer()
        return

    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.answer("⛔ Access Denied. You are not an Admin.", show_alert=True)
        return

    await query.answer()
    await state.set_state(ManageUserState.waiting_for_user_id)

    text = (
        "🔍 <b>Admin User Management</b>\n\n"
        "Please send the <b>Telegram User ID</b> or <b>Vault ID</b> of the user you want to manage.\n"
        "<i>(Examples: <code>7437014244</code> or <code>VLT-7437014244</code>)</i>\n\n"
        "Type /cancel to abort at any time."
    )

    await query.message.edit_text(text)


# ===========================================================================
# Step 2: Handle Search & Display User Profile Ticket
# ===========================================================================

@router.message(ManageUserState.waiting_for_user_id, F.text == "/cancel")
async def cmd_cancel_manage_user(message: Message, state: FSMContext) -> None:
    """Cancel user management flow."""
    await state.clear()
    from .keyboards import admin_dashboard_keyboard
    await message.answer("❌ User management flow cancelled.", reply_markup=admin_dashboard_keyboard())


@router.message(ManageUserState.waiting_for_user_id)
async def handle_user_id_input(message: Message, state: FSMContext) -> None:
    """Receive input, parse ID, fetch profile from DB, and render management card."""
    user_id = message.from_user.id if message.from_user else 0
    if not is_admin(user_id):
        return

    if not message.text:
        await message.answer("⚠️ Please send a valid User ID as text.")
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

    await state.clear()

    # Determine ban status (check DB document and in-memory cache)
    banned_in_db = bool(user_data.get("is_banned", False))
    banned_in_cache = is_user_banned(target_id_str)
    banned = banned_in_db or banned_in_cache

    first_name = user_data.get("first_name", "N/A")
    username = user_data.get("username")
    username_str = f"@{username}" if username else "None"
    sparks = user_data.get("spark_balance", 0)
    total_orders = user_data.get("total_orders", 0)
    status_text = "🔴 <b>BANNED (Suspended)</b>" if banned else "🟢 <b>ACTIVE (Normal)</b>"

    text = (
        "👤 <b>User Management Profile</b>\n\n"
        f"📛 <b>Name:</b> {first_name} ({username_str})\n"
        f"🆔 <b>User ID:</b> <code>{target_id_str}</code>\n"
        f"🔑 <b>Vault ID:</b> <code>VLT-{target_id_str}</code>\n"
        f"🪙 <b>Spark Balance:</b> <code>{sparks:,} Sparks</code>\n"
        f"📦 <b>Total Orders:</b> <code>{total_orders:,}</code>\n"
        f"📌 <b>Status:</b> {status_text}"
    )

    await message.answer(text, reply_markup=user_manage_keyboard(target_id_str, banned))


# ===========================================================================
# Step 3: Ban & Unban Callbacks
# ===========================================================================

@router.callback_query(F.data.startswith("admin_ban_user:"))
async def cb_ban_user(query: CallbackQuery) -> None:
    """Ban target user, update Firestore, and refresh in-memory cache."""
    if not query.message or not hasattr(query.message, "edit_text"):
        await query.answer()
        return

    admin_id = query.from_user.id
    if not is_admin(admin_id):
        await query.answer("⛔ Access Denied.", show_alert=True)
        return

    target_id = query.data.split(":")[1]

    try:
        await ban_user(target_id)
        add_to_ban_cache(target_id)
        await query.answer(f"🚫 User {target_id} has been BANNED.", show_alert=True)

        user_data = await get_user(target_id) or {}
        first_name = user_data.get("first_name", "N/A")
        username = user_data.get("username")
        username_str = f"@{username}" if username else "None"
        sparks = user_data.get("spark_balance", 0)
        total_orders = user_data.get("total_orders", 0)

        text = (
            "👤 <b>User Management Profile</b>\n\n"
            f"📛 <b>Name:</b> {first_name} ({username_str})\n"
            f"🆔 <b>User ID:</b> <code>{target_id}</code>\n"
            f"🔑 <b>Vault ID:</b> <code>VLT-{target_id}</code>\n"
            f"🪙 <b>Spark Balance:</b> <code>{sparks:,} Sparks</code>\n"
            f"📦 <b>Total Orders:</b> <code>{total_orders:,}</code>\n"
            f"📌 <b>Status:</b> 🔴 <b>BANNED (Suspended)</b>"
        )

        await query.message.edit_text(text, reply_markup=user_manage_keyboard(target_id, is_banned=True))
    except Exception as err:
        logger.error("Failed to ban user %s: %s", target_id, err)
        await query.answer("⚠️ Failed to update ban status in database.", show_alert=True)


@router.callback_query(F.data.startswith("admin_unban_user:"))
async def cb_unban_user(query: CallbackQuery) -> None:
    """Unban target user, update Firestore, and refresh in-memory cache."""
    if not query.message or not hasattr(query.message, "edit_text"):
        await query.answer()
        return

    admin_id = query.from_user.id
    if not is_admin(admin_id):
        await query.answer("⛔ Access Denied.", show_alert=True)
        return

    target_id = query.data.split(":")[1]

    try:
        await unban_user(target_id)
        remove_from_ban_cache(target_id)
        await query.answer(f"✅ User {target_id} has been UNBANNED.", show_alert=True)

        user_data = await get_user(target_id) or {}
        first_name = user_data.get("first_name", "N/A")
        username = user_data.get("username")
        username_str = f"@{username}" if username else "None"
        sparks = user_data.get("spark_balance", 0)
        total_orders = user_data.get("total_orders", 0)

        text = (
            "👤 <b>User Management Profile</b>\n\n"
            f"📛 <b>Name:</b> {first_name} ({username_str})\n"
            f"🆔 <b>User ID:</b> <code>{target_id}</code>\n"
            f"🔑 <b>Vault ID:</b> <code>VLT-{target_id}</code>\n"
            f"🪙 <b>Spark Balance:</b> <code>{sparks:,} Sparks</code>\n"
            f"📦 <b>Total Orders:</b> <code>{total_orders:,}</code>\n"
            f"📌 <b>Status:</b> 🟢 <b>ACTIVE (Normal)</b>"
        )

        await query.message.edit_text(text, reply_markup=user_manage_keyboard(target_id, is_banned=False))
    except Exception as err:
        logger.error("Failed to unban user %s: %s", target_id, err)
        await query.answer("⚠️ Failed to update unban status in database.", show_alert=True)
