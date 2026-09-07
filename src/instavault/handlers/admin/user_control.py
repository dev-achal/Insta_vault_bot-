"""
admin_panel/user_control.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Advanced User Control Center — Full administrative control over any user.

Provides a comprehensive admin dashboard for deep user management:
search by Telegram ID / Vault ID, view full profile with every Firestore
field, modify Spark balances, toggle bans, manage VIP status, view
paginated order history, reset cooldowns, and send direct messages.

Architecture
~~~~~~~~~~~~
  • Single FSM (``UserControlState``) with 5 states for multi-step input flows.
  • Every handler validates admin access via ``is_admin()`` before proceeding.
  • All Spark-modifying operations log to the immutable transaction ledger
    with ``admin_{action}_{admin_id}`` in the source field → full audit trail.
  • Target user ID is encoded in callback data (``uc_{action}:{uid}``) and
    persisted in FSM state data to prevent cross-request confusion.
  • Callback prefix convention:
      ``uc_``   — primary actions (view orders, toggle ban, etc.)
      ``ucc_``  — confirmation callbacks (confirm add, confirm deduct)
      ``ucr_``  — reset sub-menu and reset confirmations

Sections
~~~~~~~~
  §1  Constants, FSM States & Helper Functions
  §2  Entry Point — User ID Input & Cancel Handlers
  §3  Full Profile Card Renderer & Control Keyboard
  §4  View Orders — Paginated (reuses ``get_user_orders`` from DB layer)
  §5  Add Sparks — FSM Input → Confirmation → Atomic Execute
  §6  Deduct Sparks — FSM Input → Balance Check → Confirmation → Execute
  §7  Set Exact Balance — FSM Input → Delta Preview → Execute
  §8  Ban / Unban Toggle (Firestore + In-Memory Cache Sync)
  §9  Toggle VIP Status
  §10 Send Direct Message — FSM Input → Preview → Send via Bot API
  §11 Reset Fields Sub-Menu — Confirm-then-Execute Pattern
  §12 Refresh Profile (Cache-Busting Re-fetch)
  §13 Coming Soon Placeholder Buttons
"""

from __future__ import annotations

import html
import logging
from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from instavault.core import config
from instavault.database.db_manager import (
    ban_user,
    deduct_spark_balance,
    get_user,
    get_user_orders,
    increment_spark_balance,
    log_transaction,
    unban_user,
    update_user,
)
from instavault.database.redis_manager import invalidate_user_cache
from instavault.middlewares.ban_check import (
    add_to_ban_cache,
    is_user_banned,
    remove_from_ban_cache,
)
from instavault.utils.helpers import format_timestamp, get_ist_now

logger = logging.getLogger(__name__)
router = Router(name="admin_user_control")


# ===========================================================================
# §1  CONSTANTS, FSM STATES & HELPER FUNCTIONS
# ---------------------------------------------------------------------------
# Shared constants and utility functions used across every section of this
# module. Centralised here to avoid magic strings and duplicated logic.
# ===========================================================================

# ── Order History Display Maps ────────────────────────────────────────────
# Mirrors main_menu.py for consistent look & feel, with additional statuses
# that can appear on admin-approved orders.

_STATUS_EMOJI: dict[str, str] = {
    "pending": "⏳ Pending",
    "pending_approval": "📋 Pending Approval",
    "processing": "🔄 Processing",
    "in_progress": "🔄 In Progress",
    "delivered": "✅ Delivered",
    "cancelled": "❌ Cancelled",
    "partial": "⚠️ Partial",
    "error": "🔴 Error",
}

_PKG_LABEL: dict[str, str] = {
    "starter": "🌱 Starter",
    "growth": "🔥 Growth",
    "pro": "💎 Pro",
    "mega": "⚡ Mega",
}

_ORDERS_PER_PAGE = 5

# ── Spark Operation Safety Cap ────────────────────────────────────────────
_MAX_SPARK_AMOUNT = 1_000_000

# ── Resettable Fields ─────────────────────────────────────────────────────
# Mapping: key → (Button Label, Firestore field name, Reset-to value).
# ``None`` means the field is set to ``null`` in Firestore.

_RESET_FIELDS: dict[str, tuple[str, str, Any]] = {
    "mystery_box": ("🎁 Mystery Box Cooldown", "last_mystery_box_date", None),
    "shortener": ("🔗 Shortener Task Date", "last_shortener_task_date", None),
    "ig_handle": ("📸 Instagram Handle", "instagram_handle", None),
    "power_score": ("📊 Power Score", "power_score", 0),
}

# ── Coming-Soon Callback Data Set ─────────────────────────────────────────
_COMING_SOON_UC = {
    "uc_analytics",
    "uc_rank_system",
}


# ---------------------------------------------------------------------------
# FSM States — Multi-step admin input flows
# ---------------------------------------------------------------------------


class UserControlState(StatesGroup):
    """Finite-state-machine states for the User Control Center.

    Each state guards a ``Message`` handler that captures typed admin input
    (user ID, spark amount, or direct-message text).
    """

    waiting_for_user_id = State()  # Step 1: admin types Telegram ID or VLT-ID
    waiting_for_add_amount = State()  # ➕ Add Sparks: admin types amount
    waiting_for_deduct_amount = State()  # ➖ Deduct Sparks: admin types amount
    waiting_for_set_amount = State()  # 🪙 Set Balance: admin types exact amount
    waiting_for_direct_msg = State()  # 📤 Send Message: admin types message text


# ---------------------------------------------------------------------------
# Shared helper functions
# ---------------------------------------------------------------------------


def _is_admin(user_id: int) -> bool:
    """Check whether ``user_id`` is in the configured admin list."""
    return user_id in config.ADMIN_IDS


def _can_edit(query: CallbackQuery) -> bool:
    """Return ``True`` if the callback query's message supports ``edit_text``.

    Telegram sends ``InaccessibleMessage`` for messages older than 48 hours
    — those lack ``edit_text``.  This guard prevents ``AttributeError``.
    """
    return bool(query.message and hasattr(query.message, "edit_text"))


def _back_to_control_kb(uid: str) -> InlineKeyboardMarkup:
    """Single-button keyboard: 🔙 Back to User Control."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔙 Back to User Control",
                    callback_data=f"uc_profile:{uid}",
                )
            ],
        ]
    )


# ===========================================================================
# §3  FULL PROFILE CARD RENDERER & CONTROL KEYBOARD
# ---------------------------------------------------------------------------
# Renders every Firestore user field in a structured, emoji-labelled card
# and builds the dynamic action-button grid below it.
# ===========================================================================


def _render_profile_card(user_data: dict[str, Any], uid: str) -> str:
    """Build the full-detail profile card text from a Firestore user document.

    Displays all 25+ fields grouped into logical sections:
    Identity, Economy, Orders & Activity, Referrals, Flags.
    """
    # ── Identity ──────────────────────────────────────────────────────────
    first_name = html.escape(str(user_data.get("first_name", "N/A")))
    username = user_data.get("username")
    username_s = f"@{username}" if username else "None"
    vault_id = user_data.get("vault_id", f"VLT-{uid}")
    source_tag = user_data.get("source_tag", "direct")
    join_date = user_data.get("created_at") or user_data.get("join_date")
    join_fmt = format_timestamp(join_date, fmt="%d %b %Y, %I:%M %p")

    # ── Ban status (dual-layer check: Firestore + in-memory cache) ────────
    banned_db = bool(user_data.get("is_banned", False))
    banned_cache = is_user_banned(uid)
    is_banned = banned_db or banned_cache
    status_line = "🔴 <b>BANNED</b>" if is_banned else "🟢 <b>ACTIVE</b>"

    # ── Economy ───────────────────────────────────────────────────────────
    sparks = int(user_data.get("spark_balance", 0))
    lifetime = int(user_data.get("lifetime_sparks", 0))
    power_score = int(user_data.get("power_score", 0))
    rank_tier = user_data.get("rank_tier", "Rookie Vaulter")

    # ── Orders & Activity ─────────────────────────────────────────────────
    total_orders = int(user_data.get("total_orders", 0))
    total_views = int(user_data.get("total_views_recv", 0))
    ig_handle = user_data.get("instagram_handle")
    ig_line = f"@{ig_handle}" if ig_handle else "❌ Not Linked"
    last_login = format_timestamp(user_data.get("last_login"), fmt="%d %b %Y, %I:%M %p")
    mystery_box = user_data.get("last_mystery_box_date") or "Never"
    shortener = user_data.get("last_shortener_task_date") or "Never"

    # ── Referrals ─────────────────────────────────────────────────────────
    ref_code = user_data.get("referral_code", "—")
    referred_by = user_data.get("referred_by") or "None (Organic)"
    ref_count = int(user_data.get("referral_count", 0))

    # ── Flags ─────────────────────────────────────────────────────────────
    is_vip = "✅ Yes" if user_data.get("is_vip_member") else "❌ No"
    notif_pref = user_data.get("notif_preference", "all")
    community = "✅" if user_data.get("community_invited") else "❌"

    return (
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🎯 <b>USER CONTROL CENTER</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "👤 <b>IDENTITY</b>\n"
        f"├ 📛 Name: {first_name} ({username_s})\n"
        f"├ 🆔 Telegram ID: <code>{uid}</code>\n"
        f"├ 🔑 Vault ID: <code>{vault_id}</code>\n"
        f"├ 📌 Status: {status_line}\n"
        f"├ 🏷️ Source: {source_tag}\n"
        f"└ 🕐 Joined: {join_fmt}\n\n"
        "💰 <b>ECONOMY</b>\n"
        f"├ 🪙 Balance: <b>{sparks:,} Sparks</b>\n"
        f"├ 💎 Lifetime: <b>{lifetime:,} Sparks</b>\n"
        f"├ ⚡ Power Score: {power_score:,}\n"
        f"└ 🏅 Rank: {rank_tier}\n\n"
        "📦 <b>ORDERS & ACTIVITY</b>\n"
        f"├ 📊 Total Orders: {total_orders:,}\n"
        f"├ 👀 Views Received: {total_views:,}\n"
        f"├ 📸 Instagram: {ig_line}\n"
        f"├ 🕐 Last Login: {last_login}\n"
        f"├ 🎁 Mystery Box: {mystery_box}\n"
        f"└ 🔗 Shortener: {shortener}\n\n"
        "👥 <b>REFERRALS</b>\n"
        f"├ 🎟️ Code: <code>{ref_code}</code>\n"
        f"├ 📨 Referred By: {referred_by}\n"
        f"└ 👥 Invited: {ref_count}\n\n"
        "⚙️ <b>FLAGS</b>\n"
        f"├ 👑 VIP: {is_vip}\n"
        f"├ 🔔 Notifications: {notif_pref}\n"
        f"└ 🏘️ Community: {community}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )


def _build_control_keyboard(
    uid: str,
    is_banned: bool,
    is_vip: bool,
) -> InlineKeyboardMarkup:
    """Build the dynamic action-button grid below the profile card.

    Button labels for Ban and VIP change based on current user state
    so the admin always sees what the *next action* will do.
    """
    ban_btn = (
        InlineKeyboardButton(text="✅ Unban User", callback_data=f"uc_toggle_ban:{uid}")
        if is_banned
        else InlineKeyboardButton(
            text="🚫 Ban User", callback_data=f"uc_toggle_ban:{uid}"
        )
    )
    vip_btn = (
        InlineKeyboardButton(text="👑 Revoke VIP", callback_data=f"uc_toggle_vip:{uid}")
        if is_vip
        else InlineKeyboardButton(
            text="👑 Grant VIP", callback_data=f"uc_toggle_vip:{uid}"
        )
    )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            # Row 1 — Data Views
            [
                InlineKeyboardButton(
                    text="📦 View Orders", callback_data=f"uc_orders:{uid}:0"
                ),
                InlineKeyboardButton(
                    text="💰 Transactions", callback_data=f"uc_tx:{uid}:0"
                ),
            ],
            # Row 2 — Spark Economy: Add & Deduct
            [
                InlineKeyboardButton(
                    text="➕ Add Sparks", callback_data=f"uc_add_sparks:{uid}"
                ),
                InlineKeyboardButton(
                    text="➖ Deduct Sparks", callback_data=f"uc_deduct_sparks:{uid}"
                ),
            ],
            # Row 3 — Spark Economy: Set & Ban Control
            [
                InlineKeyboardButton(
                    text="🪙 Set Balance", callback_data=f"uc_set_balance:{uid}"
                ),
                ban_btn,
            ],
            # Row 4 — Status Toggles & Messaging
            [
                vip_btn,
                InlineKeyboardButton(
                    text="📤 Send Message", callback_data=f"uc_send_msg:{uid}"
                ),
            ],
            # Row 5 — Maintenance
            [
                InlineKeyboardButton(
                    text="🔄 Reset Fields", callback_data=f"uc_reset_menu:{uid}"
                ),
                InlineKeyboardButton(
                    text="🔃 Refresh", callback_data=f"uc_refresh:{uid}"
                ),
            ],
            # Row 6 — Coming Soon
            [
                InlineKeyboardButton(
                    text="📊 Analytics 🔜", callback_data="uc_analytics"
                ),
                InlineKeyboardButton(
                    text="🏷️ Rank System 🔜", callback_data="uc_rank_system"
                ),
            ],
            # Row 7 — Navigation
            [
                InlineKeyboardButton(
                    text="🔙 Back to Admin Panel", callback_data="admin_dashboard"
                ),
            ],
        ]
    )


async def _show_user_control(
    uid: str,
    message: Message,
    edit: bool = True,
) -> None:
    """Fetch user data from DB and render the full profile + control keyboard.

    This is the central rendering function called after every action
    (ban, spark change, VIP toggle, etc.) to show the updated state.
    """
    user_data = await get_user(uid)
    if not user_data:
        text = (
            f"⚠️ <b>User Not Found.</b>\n"
            f"No record exists for ID: <code>{uid}</code>"
        )
        from instavault.keyboards.admin import admin_back_keyboard

        if edit:
            await message.edit_text(text, reply_markup=admin_back_keyboard())
        else:
            await message.answer(text, reply_markup=admin_back_keyboard())
        return

    is_banned = bool(user_data.get("is_banned", False)) or is_user_banned(uid)
    is_vip = bool(user_data.get("is_vip_member", False))

    card_text = _render_profile_card(user_data, uid)
    keyboard = _build_control_keyboard(uid, is_banned, is_vip)

    if edit:
        await message.edit_text(card_text, reply_markup=keyboard)
    else:
        await message.answer(card_text, reply_markup=keyboard)


# ===========================================================================
# §2  ENTRY POINT — USER ID INPUT & CANCEL HANDLERS
# ---------------------------------------------------------------------------
# Admin clicks "🎯 User Control Center" on the dashboard → enters FSM →
# types a Telegram User ID or VLT-ID → profile card is displayed.
#
# Callbacks handled:
#   uc_start  — initiates the FSM flow (from dashboard button)
# ===========================================================================


@router.callback_query(F.data == "uc_start")
async def cb_start_user_control(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    """Dashboard entry: prompt admin to enter a User ID or Vault ID."""
    if not _can_edit(query):
        await query.answer()
        return

    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Access Denied. You are not an Admin.", show_alert=True)
        return

    await query.answer()
    await state.clear()
    await state.set_state(UserControlState.waiting_for_user_id)

    text = (
        "🎯 <b>User Control Center</b>\n\n"
        "Enter the <b>Telegram User ID</b> or <b>Vault ID</b> "
        "of the user you want to manage.\n\n"
        "<i>Examples:</i>\n"
        "• <code>7437014244</code>\n"
        "• <code>VLT-7437014244</code>\n\n"
        "Type /cancel to abort."
    )
    await query.message.edit_text(text)


# ── /cancel — Abort any active User Control FSM flow ─────────────────────


@router.message(UserControlState.waiting_for_user_id, F.text == "/cancel")
@router.message(UserControlState.waiting_for_add_amount, F.text == "/cancel")
@router.message(UserControlState.waiting_for_deduct_amount, F.text == "/cancel")
@router.message(UserControlState.waiting_for_set_amount, F.text == "/cancel")
@router.message(UserControlState.waiting_for_direct_msg, F.text == "/cancel")
async def cmd_cancel_user_control(
    message: Message,
    state: FSMContext,
) -> None:
    """Cancel any active User Control Center FSM flow and return to dashboard."""
    await state.clear()
    from instavault.keyboards.admin import admin_dashboard_keyboard

    await message.answer(
        "❌ User Control operation cancelled.",
        reply_markup=admin_dashboard_keyboard(),
    )


# ── Step 2: Receive & validate User ID input ─────────────────────────────


@router.message(UserControlState.waiting_for_user_id)
async def handle_user_id_input(
    message: Message,
    state: FSMContext,
) -> None:
    """Parse the admin's input, resolve the target user, and render the
    full profile card with action buttons.
    """
    if not _is_admin(message.from_user.id if message.from_user else 0):
        return

    if not message.text:
        await message.answer("⚠️ Please send a valid User ID as text.")
        return

    # Normalise: strip whitespace, remove "VLT-" prefix if present
    raw = message.text.strip().upper()
    target_id = raw.replace("VLT-", "").replace("VLT", "").strip()

    if not target_id.isdigit():
        await message.answer(
            "⚠️ <b>Invalid ID Format.</b> Send a numeric Telegram User ID "
            "or Vault ID.\n"
            "Example: <code>7437014244</code>"
        )
        return

    # Verify user exists in database
    user_data = await get_user(target_id)
    if not user_data:
        await message.answer(
            f"⚠️ <b>User Not Found.</b>\n"
            f"No record in database for ID: <code>{target_id}</code>"
        )
        return  # Stay in FSM state so admin can retry

    # Success — clear FSM and render profile
    await state.clear()
    await _show_user_control(target_id, message, edit=False)


# ===========================================================================
# §4  VIEW ORDERS — PAGINATED
# ---------------------------------------------------------------------------
# Reuses ``get_user_orders()`` from the database layer with the same
# rendering format as the user-facing order history in main_menu.py.
# Admin-specific: target user ID is encoded in pagination callbacks,
# and the back button returns to the User Control panel (not user profile).
#
# Callbacks handled:
#   uc_orders:{uid}:{page}       — initial order list view
#   uc_orders_page:{uid}:{page}  — pagination (prev/next navigation)
# ===========================================================================


def _order_history_keyboard(
    uid: str,
    has_prev: bool,
    has_next: bool,
    page: int,
) -> InlineKeyboardMarkup:
    """Build pagination keyboard for admin order history view."""
    rows: list[list[InlineKeyboardButton]] = []

    # ── Prev / Next row ───────────────────────────────────────────────────
    nav_row: list[InlineKeyboardButton] = []
    if has_prev:
        nav_row.append(
            InlineKeyboardButton(
                text="⬅️ Prev",
                callback_data=f"uc_orders_page:{uid}:{page - 1}",
            )
        )
    if has_next:
        nav_row.append(
            InlineKeyboardButton(
                text="Next ➡️",
                callback_data=f"uc_orders_page:{uid}:{page + 1}",
            )
        )
    if nav_row:
        rows.append(nav_row)

    rows.append(
        [
            InlineKeyboardButton(
                text="🔙 Back to User Control",
                callback_data=f"uc_profile:{uid}",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _render_admin_orders(
    uid: str,
    message: Message,
    edit: bool,
    page: int = 0,
) -> None:
    """Fetch and render paginated order history for the target user.

    Rendering format mirrors ``main_menu._render_order_history`` for
    visual consistency, but callbacks route back to the User Control panel.
    """
    user_data = await get_user(uid)
    if not user_data:
        return

    total = int(user_data.get("total_orders", 0))

    # ── Empty state ───────────────────────────────────────────────────────
    if total == 0:
        text = (
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 <b>ORDERS — User {uid}</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "📭 This user has no orders yet.\n"
            "━━━━━━━━━━━━━━━━━━━━━━━"
        )
        kb = _back_to_control_kb(uid)
        if edit:
            await message.edit_text(text, reply_markup=kb)
        else:
            await message.answer(text, reply_markup=kb)
        return

    # ── Pagination math ───────────────────────────────────────────────────
    total_pages = max(1, (total + _ORDERS_PER_PAGE - 1) // _ORDERS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))

    # ── Fetch page from Firestore (server-side offset pagination) ─────────
    page_orders = await get_user_orders(uid, limit=_ORDERS_PER_PAGE, page=page)

    lines: list[str] = [
        "━━━━━━━━━━━━━━━━━━━━━━━",
        f"📦 <b>ORDERS — User {uid}</b>",
        f"<i>Page {page + 1}/{total_pages}  •  Total: {total} orders</i>",
        "━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    for idx, order in enumerate(page_orders, start=page * _ORDERS_PER_PAGE + 1):
        order_id = order.get("order_id", "—")
        pkg = _PKG_LABEL.get(
            order.get("package_type", ""),
            order.get("package_type", "—").title(),
        )
        views = int(order.get("views_ordered", 0))
        sparks = int(order.get("sparks_spent", 0))
        ig_url = order.get("instagram_url") or "—"
        status = _STATUS_EMOJI.get(order.get("status", "pending"), "🔄 Processing")
        created = format_timestamp(order.get("created_at"), fmt="%d %b %Y, %I:%M %p")

        lines += [
            "",
            f"<b>#{idx}  —  {pkg}</b>",
            f"🆔 <code>{order_id[:12]}…</code>",
            f"📅 {created} IST",
            f"👁 Views: <b>{views:,}</b>   ⚡ Cost: <b>{sparks:,}</b>",
            f"📸 {ig_url}",
            f"📊 {status}",
        ]

    lines.append("\n━━━━━━━━━━━━━━━━━━━━━━━")
    text = "\n".join(lines)

    kb = _order_history_keyboard(
        uid, has_prev=(page > 0), has_next=(page < total_pages - 1), page=page
    )
    if edit:
        await message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("uc_orders:"))
async def cb_view_orders(query: CallbackQuery) -> None:
    """Entry point: show order history for a target user (page 0)."""
    if not _can_edit(query):
        await query.answer()
        return
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Access Denied.", show_alert=True)
        return

    # uc_orders:{uid}:{page}
    parts = query.data.split(":")
    uid = parts[1]
    page = int(parts[2]) if len(parts) > 2 else 0

    await query.answer()
    await _render_admin_orders(uid, query.message, edit=True, page=page)


@router.callback_query(F.data.startswith("uc_orders_page:"))
async def cb_orders_page(query: CallbackQuery) -> None:
    """Pagination: navigate between order history pages."""
    if not _can_edit(query):
        await query.answer()
        return
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Access Denied.", show_alert=True)
        return

    # uc_orders_page:{uid}:{page}
    parts = query.data.split(":")
    uid = parts[1]
    page = int(parts[2]) if len(parts) > 2 else 0

    await query.answer()
    await _render_admin_orders(uid, query.message, edit=True, page=page)


# ===========================================================================
# §4b  VIEW TRANSACTIONS — PAGINATED (shared service)
# ---------------------------------------------------------------------------
# Uses the shared ``services.transaction_history`` module for rendering.
# Admin-specific: target user ID is encoded in pagination callbacks,
# and the back button returns to the User Control panel.
#
# Callbacks handled:
#   uc_tx:{uid}:{page}       — initial transaction list view
#   uc_tx_page:{uid}:{page}  — pagination (prev/next navigation)
# ===========================================================================

from instavault.services.transaction_history import (
    render_transaction_page,
    build_transaction_keyboard,
)


@router.callback_query(F.data.startswith("uc_tx:"))
async def cb_view_transactions(query: CallbackQuery) -> None:
    """Show paginated transaction history for a target user."""
    if not _can_edit(query):
        await query.answer()
        return
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Access Denied.", show_alert=True)
        return

    # uc_tx:{uid}:{page}
    parts = query.data.split(":")
    uid = parts[1]
    page = int(parts[2]) if len(parts) > 2 else 0

    await query.answer()

    text, _total, total_pages = await render_transaction_page(uid, page=page)
    kb = build_transaction_keyboard(
        user_id=uid,
        page=page,
        total_pages=total_pages,
        back_callback=f"uc_profile:{uid}",
        callback_prefix="uc_tx_page",
    )
    await query.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data.startswith("uc_tx_page:"))
async def cb_tx_page(query: CallbackQuery) -> None:
    """Pagination: navigate between transaction history pages (admin)."""
    if not _can_edit(query):
        await query.answer()
        return
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Access Denied.", show_alert=True)
        return

    # uc_tx_page:{uid}:{page}
    parts = query.data.split(":")
    uid = parts[1]
    page = int(parts[2]) if len(parts) > 2 else 0

    await query.answer()

    text, _total, total_pages = await render_transaction_page(uid, page=page)
    kb = build_transaction_keyboard(
        user_id=uid,
        page=page,
        total_pages=total_pages,
        back_callback=f"uc_profile:{uid}",
        callback_prefix="uc_tx_page",
    )
    await query.message.edit_text(text, reply_markup=kb)


# ===========================================================================
# §5  ADD SPARKS — FSM FLOW
# ---------------------------------------------------------------------------
# Flow: Admin clicks ➕ Add Sparks → FSM asks for amount → admin types
# a positive integer → confirmation card with current/new balance →
# admin clicks ✅ Confirm → atomic increment + transaction log.
#
# Callbacks handled:
#   uc_add_sparks:{uid}          — enter FSM
#   ucc_confirm_add:{uid}:{amt} — execute after confirmation
# ===========================================================================


@router.callback_query(F.data.startswith("uc_add_sparks:"))
async def cb_add_sparks(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    """Enter FSM: prompt admin to type the Spark amount to add."""
    if not _can_edit(query):
        await query.answer()
        return
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Access Denied.", show_alert=True)
        return

    uid = query.data.split(":")[1]
    await query.answer()
    await state.clear()
    await state.set_state(UserControlState.waiting_for_add_amount)
    await state.update_data(uc_target_id=uid)

    await query.message.edit_text(
        f"➕ <b>Add Sparks</b> — User <code>{uid}</code>\n\n"
        f"Enter the number of Sparks to add (1 – {_MAX_SPARK_AMOUNT:,}).\n\n"
        "Type /cancel to abort."
    )


@router.message(UserControlState.waiting_for_add_amount)
async def handle_add_amount(message: Message, state: FSMContext) -> None:
    """Validate the typed amount and show a confirmation card."""
    if not _is_admin(message.from_user.id if message.from_user else 0):
        return
    if not message.text or not message.text.strip().isdigit():
        await message.answer(
            "⚠️ Send a positive whole number.\nExample: <code>5000</code>"
        )
        return

    amount = int(message.text.strip())
    if amount <= 0 or amount > _MAX_SPARK_AMOUNT:
        await message.answer(f"⚠️ Amount must be between 1 and {_MAX_SPARK_AMOUNT:,}.")
        return

    data = await state.get_data()
    uid = data.get("uc_target_id", "")
    await state.clear()

    # Fetch current balance for the preview
    user_data = await get_user(uid)
    if not user_data:
        await message.answer(f"⚠️ User <code>{uid}</code> not found.")
        return

    current = int(user_data.get("spark_balance", 0))

    confirm_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Confirm Add",
                    callback_data=f"ucc_confirm_add:{uid}:{amount}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Cancel",
                    callback_data=f"uc_profile:{uid}",
                )
            ],
        ]
    )

    await message.answer(
        f"⚡ <b>Confirm: Add Sparks</b>\n\n"
        f"👤 User: <code>{uid}</code>\n"
        f"🪙 Current Balance: <b>{current:,}</b>\n"
        f"➕ Adding: <b>+{amount:,}</b>\n"
        f"💎 New Balance: <b>{current + amount:,}</b>\n\n"
        f"<i>This action is logged in the audit trail.</i>",
        reply_markup=confirm_kb,
    )


@router.callback_query(F.data.startswith("ucc_confirm_add:"))
async def cb_confirm_add(query: CallbackQuery) -> None:
    """Execute the atomic spark increment after admin confirmation."""
    if not _can_edit(query):
        await query.answer()
        return
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Access Denied.", show_alert=True)
        return

    parts = query.data.split(":")
    uid = parts[1]
    amount = int(parts[2])

    # Re-verify user exists (guard against stale confirm buttons)
    if not await get_user(uid):
        await query.answer("⚠️ User no longer exists.", show_alert=True)
        return

    try:
        await increment_spark_balance(uid, amount)
        await log_transaction(uid, "bonus", amount, f"admin_grant_{query.from_user.id}")
        logger.info(
            "Admin %s added %d Sparks to user %s",
            query.from_user.id,
            amount,
            uid,
        )
        await query.answer(f"✅ +{amount:,} Sparks added!", show_alert=True)
    except Exception as err:
        logger.error("Failed to add sparks to %s: %s", uid, err)
        await query.answer("⚠️ Database error. Please retry.", show_alert=True)
        return

    await _show_user_control(uid, query.message, edit=True)


# ===========================================================================
# §6  DEDUCT SPARKS — FSM FLOW
# ---------------------------------------------------------------------------
# Same pattern as §5 but includes a balance check before confirmation.
# Uses ``deduct_spark_balance()`` which only decrements ``spark_balance``
# (does NOT reduce ``lifetime_sparks`` — lifetime is a high-water mark).
#
# Callbacks handled:
#   uc_deduct_sparks:{uid}          — enter FSM
#   ucc_confirm_deduct:{uid}:{amt} — execute after confirmation
# ===========================================================================


@router.callback_query(F.data.startswith("uc_deduct_sparks:"))
async def cb_deduct_sparks(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    """Enter FSM: prompt admin to type the Spark amount to deduct."""
    if not _can_edit(query):
        await query.answer()
        return
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Access Denied.", show_alert=True)
        return

    uid = query.data.split(":")[1]
    await query.answer()
    await state.clear()
    await state.set_state(UserControlState.waiting_for_deduct_amount)
    await state.update_data(uc_target_id=uid)

    await query.message.edit_text(
        f"➖ <b>Deduct Sparks</b> — User <code>{uid}</code>\n\n"
        f"Enter the number of Sparks to deduct (1 – {_MAX_SPARK_AMOUNT:,}).\n\n"
        "Type /cancel to abort."
    )


@router.message(UserControlState.waiting_for_deduct_amount)
async def handle_deduct_amount(message: Message, state: FSMContext) -> None:
    """Validate amount, check balance, and show confirmation card."""
    if not _is_admin(message.from_user.id if message.from_user else 0):
        return
    if not message.text or not message.text.strip().isdigit():
        await message.answer(
            "⚠️ Send a positive whole number.\nExample: <code>3000</code>"
        )
        return

    amount = int(message.text.strip())
    if amount <= 0 or amount > _MAX_SPARK_AMOUNT:
        await message.answer(f"⚠️ Amount must be between 1 and {_MAX_SPARK_AMOUNT:,}.")
        return

    data = await state.get_data()
    uid = data.get("uc_target_id", "")
    await state.clear()

    user_data = await get_user(uid)
    if not user_data:
        await message.answer(f"⚠️ User <code>{uid}</code> not found.")
        return

    current = int(user_data.get("spark_balance", 0))

    # ── Balance guard: prevent negative balance ───────────────────────────
    if current < amount:
        await message.answer(
            f"⚠️ <b>Insufficient Balance.</b>\n\n"
            f"User has <b>{current:,}</b> Sparks but you are trying "
            f"to deduct <b>{amount:,}</b>.\n\n"
            f"Maximum you can deduct: <b>{current:,}</b>",
            reply_markup=_back_to_control_kb(uid),
        )
        return

    confirm_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Confirm Deduct",
                    callback_data=f"ucc_confirm_deduct:{uid}:{amount}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Cancel",
                    callback_data=f"uc_profile:{uid}",
                )
            ],
        ]
    )

    await message.answer(
        f"⚡ <b>Confirm: Deduct Sparks</b>\n\n"
        f"👤 User: <code>{uid}</code>\n"
        f"🪙 Current Balance: <b>{current:,}</b>\n"
        f"➖ Deducting: <b>-{amount:,}</b>\n"
        f"💎 New Balance: <b>{current - amount:,}</b>\n\n"
        f"<i>This action is logged in the audit trail.</i>",
        reply_markup=confirm_kb,
    )


@router.callback_query(F.data.startswith("ucc_confirm_deduct:"))
async def cb_confirm_deduct(query: CallbackQuery) -> None:
    """Execute the atomic spark deduction after admin confirmation."""
    if not _can_edit(query):
        await query.answer()
        return
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Access Denied.", show_alert=True)
        return

    parts = query.data.split(":")
    uid = parts[1]
    amount = int(parts[2])

    # Re-verify balance at execution time (race-condition safeguard)
    user_data = await get_user(uid)
    if not user_data:
        await query.answer("⚠️ User no longer exists.", show_alert=True)
        return

    current = int(user_data.get("spark_balance", 0))
    if current < amount:
        await query.answer(
            f"⚠️ Balance changed! Now {current:,} — cannot deduct {amount:,}.",
            show_alert=True,
        )
        await _show_user_control(uid, query.message, edit=True)
        return

    try:
        await deduct_spark_balance(uid, amount)
        await log_transaction(
            uid, "spend", amount, f"admin_deduct_{query.from_user.id}"
        )
        logger.info(
            "Admin %s deducted %d Sparks from user %s",
            query.from_user.id,
            amount,
            uid,
        )
        await query.answer(f"✅ -{amount:,} Sparks deducted!", show_alert=True)
    except Exception as err:
        logger.error("Failed to deduct sparks from %s: %s", uid, err)
        await query.answer("⚠️ Database error. Please retry.", show_alert=True)
        return

    await _show_user_control(uid, query.message, edit=True)


# ===========================================================================
# §7  SET EXACT BALANCE — FSM FLOW
# ---------------------------------------------------------------------------
# Allows admin to forcefully set a user's ``spark_balance`` to an exact
# value. Unlike Add/Deduct, this does NOT modify ``lifetime_sparks`` —
# it is a direct override. The delta (Δ) is shown in the confirmation
# card for transparency.
#
# Callbacks handled:
#   uc_set_balance:{uid}          — enter FSM
#   ucc_confirm_set:{uid}:{amt}  — execute after confirmation
# ===========================================================================


@router.callback_query(F.data.startswith("uc_set_balance:"))
async def cb_set_balance(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    """Enter FSM: prompt admin to type the exact balance to set."""
    if not _can_edit(query):
        await query.answer()
        return
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Access Denied.", show_alert=True)
        return

    uid = query.data.split(":")[1]
    await query.answer()
    await state.clear()
    await state.set_state(UserControlState.waiting_for_set_amount)
    await state.update_data(uc_target_id=uid)

    await query.message.edit_text(
        f"🪙 <b>Set Exact Balance</b> — User <code>{uid}</code>\n\n"
        f"Enter the exact Spark balance to set (0 – {_MAX_SPARK_AMOUNT:,}).\n\n"
        "Type /cancel to abort."
    )


@router.message(UserControlState.waiting_for_set_amount)
async def handle_set_amount(message: Message, state: FSMContext) -> None:
    """Validate input and show a delta-preview confirmation card."""
    if not _is_admin(message.from_user.id if message.from_user else 0):
        return
    if not message.text or not message.text.strip().isdigit():
        await message.answer(
            "⚠️ Send a non-negative whole number.\nExample: <code>10000</code>"
        )
        return

    new_amount = int(message.text.strip())
    if new_amount > _MAX_SPARK_AMOUNT:
        await message.answer(f"⚠️ Maximum balance: {_MAX_SPARK_AMOUNT:,}.")
        return

    data = await state.get_data()
    uid = data.get("uc_target_id", "")
    await state.clear()

    user_data = await get_user(uid)
    if not user_data:
        await message.answer(f"⚠️ User <code>{uid}</code> not found.")
        return

    current = int(user_data.get("spark_balance", 0))
    delta = new_amount - current
    delta_s = f"+{delta:,}" if delta >= 0 else f"{delta:,}"

    confirm_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Confirm Set Balance",
                    callback_data=f"ucc_confirm_set:{uid}:{new_amount}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Cancel",
                    callback_data=f"uc_profile:{uid}",
                )
            ],
        ]
    )

    await message.answer(
        f"🪙 <b>Confirm: Set Exact Balance</b>\n\n"
        f"👤 User: <code>{uid}</code>\n"
        f"🪙 Current: <b>{current:,}</b>\n"
        f"🎯 Set To: <b>{new_amount:,}</b>\n"
        f"📊 Delta: <b>{delta_s}</b>\n\n"
        f"<i>⚠️ This overrides spark_balance directly.\n"
        f"lifetime_sparks will NOT be modified.</i>",
        reply_markup=confirm_kb,
    )


@router.callback_query(F.data.startswith("ucc_confirm_set:"))
async def cb_confirm_set(query: CallbackQuery) -> None:
    """Execute the direct balance override after admin confirmation."""
    if not _can_edit(query):
        await query.answer()
        return
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Access Denied.", show_alert=True)
        return

    parts = query.data.split(":")
    uid = parts[1]
    new_amount = int(parts[2])

    user_data = await get_user(uid)
    if not user_data:
        await query.answer("⚠️ User no longer exists.", show_alert=True)
        return

    old_balance = int(user_data.get("spark_balance", 0))
    delta = abs(new_amount - old_balance)
    tx_type = "bonus" if new_amount >= old_balance else "spend"

    try:
        await update_user(uid, {"spark_balance": new_amount})
        if delta > 0:
            await log_transaction(
                uid, tx_type, delta, f"admin_set_balance_{query.from_user.id}"
            )
        logger.info(
            "Admin %s set balance for user %s: %d → %d",
            query.from_user.id,
            uid,
            old_balance,
            new_amount,
        )
        await query.answer(f"✅ Balance set to {new_amount:,}!", show_alert=True)
    except Exception as err:
        logger.error("Failed to set balance for %s: %s", uid, err)
        await query.answer("⚠️ Database error. Please retry.", show_alert=True)
        return

    await _show_user_control(uid, query.message, edit=True)


# ===========================================================================
# §8  BAN / UNBAN TOGGLE
# ---------------------------------------------------------------------------
# Instant toggle: updates Firestore ``is_banned`` field AND syncs the
# in-memory ``BANNED_USER_CACHE`` set used by the ban middleware.
# Includes self-ban protection: admins cannot ban other admins.
#
# Callback handled:
#   uc_toggle_ban:{uid}
# ===========================================================================


@router.callback_query(F.data.startswith("uc_toggle_ban:"))
async def cb_toggle_ban(query: CallbackQuery) -> None:
    """Toggle a user's ban status (Firestore + in-memory cache)."""
    if not _can_edit(query):
        await query.answer()
        return
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Access Denied.", show_alert=True)
        return

    uid = query.data.split(":")[1]

    # ── Self-ban protection ───────────────────────────────────────────────
    try:
        if int(uid) in config.ADMIN_IDS:
            await query.answer("⛔ Cannot ban an Admin account!", show_alert=True)
            return
    except ValueError:
        pass

    user_data = await get_user(uid)
    if not user_data:
        await query.answer("⚠️ User not found.", show_alert=True)
        return

    is_banned = bool(user_data.get("is_banned", False)) or is_user_banned(uid)

    try:
        if is_banned:
            # ── UNBAN ─────────────────────────────────────────────────────
            await unban_user(uid)
            remove_from_ban_cache(uid)
            logger.info("Admin %s UNBANNED user %s", query.from_user.id, uid)
            await query.answer(f"✅ User {uid} has been UNBANNED.", show_alert=True)
        else:
            # ── BAN ───────────────────────────────────────────────────────
            await ban_user(uid)
            add_to_ban_cache(uid)
            logger.info("Admin %s BANNED user %s", query.from_user.id, uid)
            await query.answer(f"🚫 User {uid} has been BANNED.", show_alert=True)
    except Exception as err:
        logger.error("Failed to toggle ban for %s: %s", uid, err)
        await query.answer("⚠️ Database error. Please retry.", show_alert=True)
        return

    await _show_user_control(uid, query.message, edit=True)


# ===========================================================================
# §9  TOGGLE VIP STATUS
# ---------------------------------------------------------------------------
# Instant toggle of the ``is_vip_member`` boolean field.
#
# Callback handled:
#   uc_toggle_vip:{uid}
# ===========================================================================


@router.callback_query(F.data.startswith("uc_toggle_vip:"))
async def cb_toggle_vip(query: CallbackQuery) -> None:
    """Toggle a user's VIP membership status."""
    if not _can_edit(query):
        await query.answer()
        return
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Access Denied.", show_alert=True)
        return

    uid = query.data.split(":")[1]

    user_data = await get_user(uid)
    if not user_data:
        await query.answer("⚠️ User not found.", show_alert=True)
        return

    current_vip = bool(user_data.get("is_vip_member", False))
    new_vip = not current_vip

    try:
        await update_user(uid, {"is_vip_member": new_vip})
        status = "GRANTED" if new_vip else "REVOKED"
        logger.info("Admin %s %s VIP for user %s", query.from_user.id, status, uid)
        await query.answer(f"👑 VIP {status} for user {uid}.", show_alert=True)
    except Exception as err:
        logger.error("Failed to toggle VIP for %s: %s", uid, err)
        await query.answer("⚠️ Database error. Please retry.", show_alert=True)
        return

    await _show_user_control(uid, query.message, edit=True)


# ===========================================================================
# §10  SEND DIRECT MESSAGE — FSM FLOW
# ---------------------------------------------------------------------------
# Admin types a message → preview is shown → confirm sends it directly
# to the target user via the Telegram Bot API (``bot.send_message``).
#
# Callbacks handled:
#   uc_send_msg:{uid}  — enter FSM
#   ucc_send_msg       — confirm and send (reads from FSM state data)
#   ucc_cancel_msg     — cancel and return to profile
# ===========================================================================


@router.callback_query(F.data.startswith("uc_send_msg:"))
async def cb_send_msg(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    """Enter FSM: prompt admin to type the message to send."""
    if not _can_edit(query):
        await query.answer()
        return
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Access Denied.", show_alert=True)
        return

    uid = query.data.split(":")[1]
    await query.answer()
    await state.clear()
    await state.set_state(UserControlState.waiting_for_direct_msg)
    await state.update_data(uc_target_id=uid)

    await query.message.edit_text(
        f"📤 <b>Send Direct Message</b> — User <code>{uid}</code>\n\n"
        "Type the message you want to send to this user.\n"
        "The message will be delivered as a bot message.\n\n"
        "Type /cancel to abort."
    )


@router.message(UserControlState.waiting_for_direct_msg)
async def handle_direct_message(message: Message, state: FSMContext) -> None:
    """Capture the admin's message text and show a send-confirmation preview."""
    if not _is_admin(message.from_user.id if message.from_user else 0):
        return
    if not message.text:
        await message.answer("⚠️ Please send a text message.")
        return

    msg_text = message.text.strip()
    if not msg_text or msg_text.startswith("/"):
        await message.answer("⚠️ Send a regular text message, not a command.")
        return

    data = await state.get_data()
    uid = data.get("uc_target_id", "")

    # Store message in FSM state for the confirm callback to read
    await state.update_data(uc_message=msg_text)

    # Escape HTML for safe preview rendering
    preview = html.escape(msg_text)
    if len(preview) > 500:
        preview = preview[:500] + "…"

    confirm_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Send Message", callback_data="ucc_send_msg"
                )
            ],
            [InlineKeyboardButton(text="❌ Cancel", callback_data="ucc_cancel_msg")],
        ]
    )

    await message.answer(
        f"📤 <b>Message Preview</b>\n\n"
        f"👤 To: <code>{uid}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{preview}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<i>Click Send to deliver this message.</i>",
        reply_markup=confirm_kb,
    )


@router.callback_query(F.data == "ucc_send_msg")
async def cb_confirm_send_msg(query: CallbackQuery, state: FSMContext) -> None:
    """Send the previewed message to the target user via Bot API."""
    if not _can_edit(query):
        await query.answer()
        return
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Access Denied.", show_alert=True)
        return

    data = await state.get_data()
    uid = data.get("uc_target_id", "")
    msg_text = data.get("uc_message", "")
    await state.clear()

    if not uid or not msg_text:
        await query.answer("⚠️ Message data lost. Please try again.", show_alert=True)
        return

    try:
        await query.message.bot.send_message(
            chat_id=int(uid),
            text=f"📬 <b>Message from Admin:</b>\n\n{html.escape(msg_text)}",
        )
        logger.info("Admin %s sent direct message to user %s", query.from_user.id, uid)
        await query.answer("✅ Message sent successfully!", show_alert=True)
    except Exception as err:
        logger.error("Failed to send DM to user %s: %s", uid, err)
        await query.answer(
            "⚠️ Failed to send. User may have blocked the bot.",
            show_alert=True,
        )

    await _show_user_control(uid, query.message, edit=True)


@router.callback_query(F.data == "ucc_cancel_msg")
async def cb_cancel_send_msg(query: CallbackQuery, state: FSMContext) -> None:
    """Cancel the direct message flow and return to the user profile."""
    if not _can_edit(query):
        await query.answer()
        return

    data = await state.get_data()
    uid = data.get("uc_target_id", "")
    await state.clear()
    await query.answer("❌ Message cancelled.")

    if uid:
        await _show_user_control(uid, query.message, edit=True)


# ===========================================================================
# §11  RESET FIELDS SUB-MENU
# ---------------------------------------------------------------------------
# Shows a sub-menu of resettable user fields. Each option leads to a
# confirmation step before executing the reset via ``update_user()``.
#
# Callbacks handled:
#   uc_reset_menu:{uid}          — show the reset options sub-menu
#   ucr_reset:{uid}:{field_key}  — show confirmation for a specific field
#   ucr_confirm:{uid}:{field_key} — execute the reset
# ===========================================================================


def _build_reset_keyboard(uid: str) -> InlineKeyboardMarkup:
    """Build the reset-fields sub-menu keyboard."""
    rows: list[list[InlineKeyboardButton]] = []

    for key, (label, _field, _val) in _RESET_FIELDS.items():
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"ucr_reset:{uid}:{key}",
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="🔙 Back to User Control",
                callback_data=f"uc_profile:{uid}",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("uc_reset_menu:"))
async def cb_reset_menu(query: CallbackQuery) -> None:
    """Display the reset-fields sub-menu."""
    if not _can_edit(query):
        await query.answer()
        return
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Access Denied.", show_alert=True)
        return

    uid = query.data.split(":")[1]
    await query.answer()

    await query.message.edit_text(
        f"🔄 <b>Reset Fields</b> — User <code>{uid}</code>\n\n"
        "Select a field to reset. A confirmation will be shown before "
        "any change is applied.\n\n"
        "<i>⚠️ Resets are immediate and cannot be undone.</i>",
        reply_markup=_build_reset_keyboard(uid),
    )


@router.callback_query(F.data.startswith("ucr_reset:"))
async def cb_reset_field_confirm(query: CallbackQuery) -> None:
    """Show a confirmation prompt before resetting a specific field."""
    if not _can_edit(query):
        await query.answer()
        return
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Access Denied.", show_alert=True)
        return

    # ucr_reset:{uid}:{field_key}
    parts = query.data.split(":")
    uid = parts[1]
    field_key = parts[2]

    if field_key not in _RESET_FIELDS:
        await query.answer("⚠️ Unknown field.", show_alert=True)
        return

    label, db_field, reset_val = _RESET_FIELDS[field_key]
    display_val = str(reset_val) if reset_val is not None else "None (empty)"

    await query.answer()

    confirm_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Yes, Reset",
                    callback_data=f"ucr_confirm:{uid}:{field_key}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Cancel",
                    callback_data=f"uc_reset_menu:{uid}",
                )
            ],
        ]
    )

    await query.message.edit_text(
        f"⚠️ <b>Confirm Reset</b>\n\n"
        f"👤 User: <code>{uid}</code>\n"
        f"🔄 Field: <b>{label}</b>\n"
        f"📝 <code>{db_field}</code> → <code>{display_val}</code>\n\n"
        f"<i>This action cannot be undone.</i>",
        reply_markup=confirm_kb,
    )


@router.callback_query(F.data.startswith("ucr_confirm:"))
async def cb_confirm_reset(query: CallbackQuery) -> None:
    """Execute the field reset after admin confirmation."""
    if not _can_edit(query):
        await query.answer()
        return
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Access Denied.", show_alert=True)
        return

    parts = query.data.split(":")
    uid = parts[1]
    field_key = parts[2]

    if field_key not in _RESET_FIELDS:
        await query.answer("⚠️ Unknown field.", show_alert=True)
        return

    label, db_field, reset_val = _RESET_FIELDS[field_key]

    try:
        await update_user(uid, {db_field: reset_val})
        logger.info(
            "Admin %s reset field '%s' for user %s → %s",
            query.from_user.id,
            db_field,
            uid,
            reset_val,
        )
        await query.answer(f"✅ {label} has been reset.", show_alert=True)
    except Exception as err:
        logger.error("Failed to reset field %s for %s: %s", db_field, uid, err)
        await query.answer("⚠️ Database error. Please retry.", show_alert=True)
        return

    await _show_user_control(uid, query.message, edit=True)


# ===========================================================================
# §12  REFRESH PROFILE & BACK-TO-PROFILE NAVIGATION
# ---------------------------------------------------------------------------
# Two closely related callbacks:
#   uc_profile:{uid}  — navigate back to the user control screen (cached read)
#   uc_refresh:{uid}  — bust the Redis cache and force a fresh Firestore read
# ===========================================================================


@router.callback_query(F.data.startswith("uc_profile:"))
async def cb_back_to_profile(query: CallbackQuery) -> None:
    """Navigate back to the User Control profile card."""
    if not _can_edit(query):
        await query.answer()
        return
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Access Denied.", show_alert=True)
        return

    uid = query.data.split(":")[1]
    await query.answer()
    await _show_user_control(uid, query.message, edit=True)


@router.callback_query(F.data.startswith("uc_refresh:"))
async def cb_refresh_profile(query: CallbackQuery) -> None:
    """Force-refresh: invalidate Redis cache and re-fetch from Firestore."""
    if not _can_edit(query):
        await query.answer()
        return
    if not _is_admin(query.from_user.id):
        await query.answer("⛔ Access Denied.", show_alert=True)
        return

    uid = query.data.split(":")[1]

    # Bust the cache so get_user() hits Firestore directly
    await invalidate_user_cache(uid)
    await query.answer("🔃 Profile refreshed from database.")
    await _show_user_control(uid, query.message, edit=True)


# ===========================================================================
# §13  COMING SOON PLACEHOLDER BUTTONS
# ---------------------------------------------------------------------------
# Buttons that are visible in the control keyboard but not yet implemented.
# Clicking them shows a Telegram alert popup explaining the feature is
# under development. Prevents "unhandled callback" errors in logs.
#
# Coming Soon features:
#   💰 View Transactions — needs get_user_transactions() in DB layer
#   📊 User Analytics    — needs aggregation engine
#   🏷️ Rank System      — needs full rank management backend
# ===========================================================================


@router.callback_query(F.data.in_(_COMING_SOON_UC))
async def cb_coming_soon_uc(query: CallbackQuery) -> None:
    """Show a 'coming soon' alert for features still under development."""
    await query.answer(
        "🚧 This feature is under development and will be available "
        "in the next update!",
        show_alert=True,
    )
