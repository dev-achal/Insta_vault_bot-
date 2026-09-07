"""
handlers/main_menu.py
~~~~~~~~~~~~~~~~~~~~~
Phase 3 — Five Core Screens & Navigation
Phase 4 — Engagement Engine: Mystery Box, Leaderboard

Screens:
  1. 🏠  Dashboard    (show_dashboard / go_dashboard / /dashboard)
  2. 🚀  Mission      (/mission — nav_mission handled by start.py)
  3. 📦  Order        (nav_order — /order handled exclusively by orders.py)
  4. 🎁  Rewards      (nav_rewards / /rewards)
  5. 📊  Profile      (nav_profile / /profile)
  6. 🎰  Daily Slot Machine  (action_mystery_box)
  7. 🏆  Leaderboard  (nav_leaderboard)

Bug Fixes (P0/P1/P2):
  - P0: cb_mystery_box no longer double-answers the callback query.
  - P1: cb_go_dashboard does NOT pre-answer; show_dashboard answers after
        rendering (so milestone popup can still show via query.answer()).
  - P1: Duplicate /order and F.text handlers removed — orders.py owns those.
"""

import html
import logging
import random
import re
from typing import Any
from instavault.core import config
from instavault.constants.rewards import PACKAGES
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from instavault.database.db_manager import (
    get_leaderboard,
    get_user,
    get_user_orders,
    update_user,
    open_mystery_box_transactional,
    CooldownActiveError,
    UserNotFoundError,
)
from instavault.keyboards.inline import (
    back_to_dashboard_keyboard,
    dashboard_keyboard,
    help_keyboard,
    leaderboard_keyboard,
    mission_center_keyboard,
    mystery_box_result_keyboard,
    order_history_keyboard,
    order_keyboard_empty,
    order_keyboard_full,
    profile_keyboard,
    referral_keyboard,
    rewards_keyboard,
)
from instavault.utils.helpers import format_timestamp, get_ist_now

logger = logging.getLogger(__name__)
router = Router(name="main_menu")


# ---------------------------------------------------------------------------
# Phase 6 — Instagram Handle Linking FSM
# ---------------------------------------------------------------------------


class ProfileState(StatesGroup):
    waiting_for_ig_handle = State()


def _clean_ig_handle(raw: str) -> str:
    """
    Strip URL noise and return only the raw Instagram username.
    Handles:
      https://www.instagram.com/achal_123/?hl=en  →  achal_123
      @achal_123                                   →  achal_123
      achal_123                                    →  achal_123
    """
    handle = raw.strip()
    handle = html.unescape(handle)
    handle = re.sub(
        r"https?://(www\.)?instagram\.com/", "", handle, flags=re.IGNORECASE
    )
    handle = re.sub(r"[/?].*", "", handle)
    handle = handle.lstrip("@").strip()

    if not re.match(r"^[A-Za-z0-9._]{1,30}$", handle):
        return ""
    return handle


# ===========================================================================
# SCREEN 1 — 🏠 Dashboard
# ===========================================================================


async def show_dashboard(
    user_id: int,
    first_name: str,
    message: Message,
    edit: bool = False,
    query: CallbackQuery | None = None,
) -> None:
    """
    Render the dashboard.
    """
    user_data = await get_user(user_id)
    if user_data is None:
        err = "⚠️ Profile not found. Please send /start to set up your Vault."
        if query:
            await query.answer()
        if edit:
            await message.edit_text(err)
        else:
            await message.answer(err)
        return

    sparks = user_data.get("spark_balance", 0)
    rank = user_data.get("rank_tier", "Rookie Vaulter")
    views = user_data.get("total_views_recv", 0)

    text = (
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "👑 <b>InstaVault Dashboard</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Namaste, <b>{first_name}</b> 👋\n\n"
        f"🪙 Balance:      <b>{sparks:,} Sparks</b>\n"
        f"⚡ Rank:         <b>{rank}</b>\n"
        f"📦 Total Views:  <b>{views:,} delivered</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔴 <b>LIVE ALERT:</b> Aaj ka Mission complete karo aur Sparks kamao!\n"
        "━━━━━━━━━━━━━━━━━━━━━━━"
    )

    if edit:
        await message.edit_text(text, reply_markup=dashboard_keyboard())
    else:
        await message.answer(text, reply_markup=dashboard_keyboard())

    if query is not None:
        await query.answer()


@router.message(Command("dashboard"))
@router.message(F.text == "🏠 Dashboard")
async def cmd_dashboard(message: Message) -> None:
    user = message.from_user
    if user:
        await show_dashboard(user.id, user.first_name or "Member", message, edit=False)


@router.callback_query(F.data == "go_dashboard")
async def cb_go_dashboard(query: CallbackQuery) -> None:
    if not query.message or not hasattr(query.message, "edit_text"):
        await query.answer()
        return
    """
    Back-to-dashboard from any sub-screen.
    """
    user = query.from_user
    if query.message and user:
        await show_dashboard(
            user.id,
            user.first_name or "Member",
            query.message,
            edit=True,
            query=query,
        )


# ===========================================================================
# SCREEN 2 — 🚀 Mission
# nav_mission callback is owned by start.py (edits in-place with Phase 3 content).
# /mission command sends a fresh message.
# ===========================================================================


@router.message(Command("mission"))
@router.message(F.text == "🎯 Mission")
async def cmd_mission(message: Message) -> None:
    await message.answer(
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ <b>MISSION CENTER</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Apne manpasand task complete karke Sparks kamao!\n\n"
        "1️⃣ <b>InstaVault App Task</b> — 400 Sparks\n"
        "2️⃣ <b>Verify You Are Human (Captcha)</b> — 500 Sparks\n"
        "━━━━━━━━━━━━━━━━━━━━━━━",
        reply_markup=mission_center_keyboard(),
    )


# ===========================================================================
# SCREEN 3 — 📦 Views Order Karo
# /order command and F.text == "📦 Order Views" are exclusively in orders.py.
# This file only owns the nav_order inline callback.
# ===========================================================================


@router.callback_query(F.data == "nav_order")
async def cb_nav_order(query: CallbackQuery) -> None:
    if not query.message or not hasattr(query.message, "edit_text"):
        await query.answer()
        return
    await query.answer()
    user_id = query.from_user.id
    await _render_order_screen(user_id, query.message, edit=True)


async def _render_order_screen(user_id: int, message: Message, edit: bool) -> None:
    """Shared order screen renderer with empty-state guard."""
    user_data = await get_user(user_id)
    sparks = user_data.get("spark_balance", 0) if user_data else 0

    # Dynamically calculate the minimum package cost
    min_cost = min(pkg["cost"] for pkg in PACKAGES.values()) if PACKAGES else 500

    if sparks < min_cost:
        text = (
            "😅 <b>Yaar, Sparks thode kam hain!</b>\n\n"
            f"Minimum needed: <b>{min_cost:,} Sparks</b>\n\n"
            "Mission complete kar ya Mystery Box khol aur Sparks kamao!"
        )
        kb = order_keyboard_empty()
    else:
        text = (
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "📦 <b>VIEWS ORDER KARO</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"💰 <b>Tera Balance:</b> {sparks:,} Sparks\n\n"
            "🛒 <b>Package Select Karo:</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━"
        )
        kb = order_keyboard_full()

    if edit:
        await message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


# ===========================================================================
# SCREEN 4 — 🎁 Rewards Center
# ===========================================================================


@router.message(Command("rewards"))
@router.message(F.text == "🏆 Rewards")
async def cmd_rewards(message: Message) -> None:
    user = message.from_user
    if not user:
        return
    await _render_rewards_screen(user.id, message, edit=False)


@router.callback_query(F.data == "nav_rewards")
async def cb_nav_rewards(query: CallbackQuery) -> None:
    if not query.message or not hasattr(query.message, "edit_text"):
        await query.answer()
        return
    await query.answer()
    await _render_rewards_screen(query.from_user.id, query.message, edit=True)


async def _render_rewards_screen(user_id: int, message: Message, edit: bool) -> None:
    user_data = await get_user(user_id)

    text = (
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🎁 <b>REWARDS CENTER</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🎰 <b>Daily Slot Machine:</b>\n"
        "• Spin the slot machine — 3 tries daily!\n"
        "• 🏆 Win (Jackpot): <b>60–100 Sparks</b>\n"
        "• 😅 Lose all 3: Still get <b>30–60 Sparks</b>\n"
        "• Completely free, resets at midnight IST\n"
        "━━━━━━━━━━━━━━━━━━━━━━━"
    )

    if edit:
        await message.edit_text(text, reply_markup=rewards_keyboard())
    else:
        await message.answer(text, reply_markup=rewards_keyboard())


# ===========================================================================
# SCREEN 5 — 📊 Mera Profile
# ===========================================================================


@router.message(Command("profile"))
@router.message(F.text == "👤 Profile")
async def cmd_profile(message: Message) -> None:
    user = message.from_user
    if not user:
        return
    await _render_profile_screen(
        user.id, user.first_name or "Member", message, edit=False
    )


@router.callback_query(F.data == "nav_profile")
async def cb_nav_profile(query: CallbackQuery) -> None:
    if not query.message or not hasattr(query.message, "edit_text"):
        await query.answer()
        return
    await query.answer()
    user = query.from_user
    await _render_profile_screen(
        user.id, user.first_name or "Member", query.message, edit=True
    )


async def _render_profile_screen(
    user_id: int, first_name: str, message: Message, edit: bool
) -> None:
    user_data = await get_user(user_id)
    if not user_data:
        err = "⚠️ Profile not found. Please send /start."
        if edit:
            await message.edit_text(err)
        else:
            await message.answer(err)
        return

    vault_id = user_data.get("vault_id", "—")
    join_date = user_data.get("created_at") or user_data.get("join_date")
    total_orders = user_data.get("total_orders", 0)
    ref_count = user_data.get("referral_count", 0)
    sparks = user_data.get("spark_balance", 0)
    rank = user_data.get("rank_tier", "Rookie Vaulter")
    ig_handle = user_data.get("instagram_handle")
    join_fmt = format_timestamp(join_date, fmt="%d %b %Y")

    if ig_handle:
        ig_line = f"📸 <b>Instagram:</b> @{ig_handle}"
    else:
        ig_line = "📸 <b>Instagram:</b> ❌ Not Linked\n\n<i>(💡 Tip: Link it below to start ordering!)</i>"

    text = (
        "🏛️ <b>VAULT PROFILE</b>\n\n"
        "<blockquote>"
        f"👤 <b>{first_name}</b>\n"
        f"🆔 <code>{vault_id}</code> | 📅 {join_fmt}"
        "</blockquote>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{ig_line}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🪙 <b>{sparks:,} Sparks</b>   •   👑 <b>{rank}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 <b>Orders:</b> {total_orders}\n"
        f"🤝 <b>Referrals:</b> {ref_count}"
    )

    if edit:
        await message.edit_text(
            text, reply_markup=profile_keyboard(ig_linked=bool(ig_handle))
        )
    else:
        await message.answer(
            text, reply_markup=profile_keyboard(ig_linked=bool(ig_handle))
        )


# ===========================================================================
# SCREEN 6 — 🎰 Daily Slot Machine  (Replaces Mystery Box)
# ---------------------------------------------------------------------------
# Flow:
#   1. User clicks "🎰 Daily Slot Machine" in Rewards Center
#   2. Cooldown check → if already claimed today, show cooldown msg
#   3. Send Telegram 🎰 slot machine dice animation
#   4. Wait ~3 sec for animation to finish
#   5. Check result: value == 64 → JACKPOT (win), anything else → lose
#   6. Win on any try → grant 60–100 random Sparks
#   7. Lose → decrement tries. If tries left, show "Spin Again" button
#   8. All 3 tries lost → consolation prize: 30–60 random Sparks
#
# Telegram 🎰 Slot Machine Values:
#   Value 64 = three 7️⃣ (Jackpot!) — all other values are non-wins.
#
# Session Tracking:
#   In-memory dict `_slot_sessions` tracks tries remaining per user.
#   Cleared after win or after all 3 tries exhausted.
#   Daily cooldown tracked via `last_mystery_box_date` in Firestore.
# ===========================================================================

# ── Slot Machine Constants ────────────────────────────────────────────────
_SLOT_JACKPOT_VALUE = 64      # Telegram's jackpot result for 🎰 dice
_SLOT_MAX_TRIES = 3           # max spins per day
_SLOT_WIN_MIN = 60            # Sparks range on win (jackpot)
_SLOT_WIN_MAX = 100
_SLOT_LOSE_MIN = 30           # consolation prize range (all 3 lost)
_SLOT_LOSE_MAX = 60

# In-memory session: user_id → tries remaining today
_slot_sessions: dict[int, int] = {}


def _spin_again_kb() -> InlineKeyboardMarkup:
    """Keyboard with a 'Spin Again' button and a Back button."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎰 Spin Again",
                    callback_data="action_mystery_box",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Back to Dashboard",
                    callback_data="go_dashboard",
                ),
            ],
        ]
    )


@router.callback_query(F.data == "action_mystery_box")
async def cb_daily_slot_machine(query: CallbackQuery) -> None:
    """Daily Slot Machine — 3 tries, jackpot (64) = win, else lose."""
    if not query.message:
        await query.answer()
        return

    user_id = query.from_user.id

    # ── 1. Cooldown check (already completed today?) ──────────────────────
    user_data = await get_user(user_id)
    if not user_data:
        await query.answer("⚠️ Profile not found. Please /start.", show_alert=True)
        return

    today_str = get_ist_now().strftime("%Y-%m-%d")
    if user_data.get("last_mystery_box_date") == today_str:
        # Check if user has tries remaining (in-memory session)
        tries_left = _slot_sessions.get(user_id, 0)
        if tries_left <= 0:
            await query.answer(
                "😅 Aaj ka Daily Slot Machine pura ho chuka! Kal wapas aana. 🌙",
                show_alert=True,
            )
            return

    # ── 2. Initialize session if first try today ──────────────────────────
    if user_id not in _slot_sessions:
        _slot_sessions[user_id] = _SLOT_MAX_TRIES

    tries_left = _slot_sessions[user_id]
    if tries_left <= 0:
        await query.answer(
            "😅 Aaj ke saare tries khatam! Kal wapas aana. 🌙",
            show_alert=True,
        )
        return

    await query.answer(f"🎰 Spinning... (Try {_SLOT_MAX_TRIES - tries_left + 1}/{_SLOT_MAX_TRIES})")

    # ── 3. Send Telegram 🎰 slot machine dice animation ──────────────────
    try:
        await query.message.edit_text(
            f"🎰 <b>DAILY SLOT MACHINE</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎯 Try <b>{_SLOT_MAX_TRIES - tries_left + 1}</b> of <b>{_SLOT_MAX_TRIES}</b>\n\n"
            f"<i>Spinning the reels...</i> 🎰"
        )
    except Exception:
        pass  # edit_text can fail if message was already deleted

    dice_msg = await query.message.answer_dice(emoji="🎰")
    dice_value = dice_msg.dice.value

    # ── 4. Wait for slot machine animation (~3 sec) ───────────────────────
    import asyncio
    await asyncio.sleep(3)

    # ── 5. Decrement try count ────────────────────────────────────────────
    _slot_sessions[user_id] = tries_left - 1
    remaining = _slot_sessions[user_id]

    # ── 6. Check result ───────────────────────────────────────────────────
    if dice_value == _SLOT_JACKPOT_VALUE:
        # 🏆 JACKPOT! User won — grant 60-100 Sparks
        won_sparks = random.randint(_SLOT_WIN_MIN, _SLOT_WIN_MAX)

        try:
            await open_mystery_box_transactional(user_id, won_sparks=won_sparks)
        except CooldownActiveError:
            # Edge case: another device claimed it between tries
            await query.message.answer(
                "✅ Aaj ka reward pehle hi claim ho chuka hai!",
                reply_markup=back_to_dashboard_keyboard(),
            )
            _slot_sessions.pop(user_id, None)
            return
        except UserNotFoundError:
            await query.message.answer("⚠️ Profile not found. Please /start.")
            return

        _slot_sessions.pop(user_id, None)  # Clear session

        await query.message.answer(
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🎰 <b>JACKPOT! 🏆</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🎯 Three 7️⃣s in a row!\n"
            f"🎉 Tujhe mila: <b>{won_sparks} Sparks!</b> ⚡\n\n"
            "Kal wapas aana naye slot ke liye! 😄\n"
            "━━━━━━━━━━━━━━━━━━━━━━━",
            reply_markup=mystery_box_result_keyboard(),
        )
        return

    # ── 7. Lost this try ──────────────────────────────────────────────────
    if remaining > 0:
        # Still have tries left — show Spin Again button
        await query.message.answer(
            f"😅 <b>No Jackpot this time!</b>\n\n"
            f"🎯 Tries remaining: <b>{remaining}/{_SLOT_MAX_TRIES}</b>\n\n"
            "<i>Try again — you might hit the jackpot! 🍀</i>",
            reply_markup=_spin_again_kb(),
        )
    else:
        # All 3 tries exhausted — consolation prize: 30-60 Sparks
        consolation = random.randint(_SLOT_LOSE_MIN, _SLOT_LOSE_MAX)

        try:
            await open_mystery_box_transactional(user_id, won_sparks=consolation)
        except CooldownActiveError:
            await query.message.answer(
                "✅ Aaj ka reward pehle hi claim ho chuka hai!",
                reply_markup=back_to_dashboard_keyboard(),
            )
            _slot_sessions.pop(user_id, None)
            return
        except UserNotFoundError:
            await query.message.answer("⚠️ Profile not found. Please /start.")
            return

        _slot_sessions.pop(user_id, None)  # Clear session

        await query.message.answer(
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🎰 <b>BETTER LUCK NEXT TIME!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "😅 Teeno tries mein jackpot nahi aaya...\n"
            f"🎁 Consolation Prize: <b>{consolation} Sparks!</b> ⚡\n\n"
            "Kal wapas aana — jackpot zaroor milega! 🍀\n"
            "━━━━━━━━━━━━━━━━━━━━━━━",
            reply_markup=mystery_box_result_keyboard(),
        )


# ===========================================================================
# SCREEN 7 — 🏆 Leaderboard  (Phase 4)
# ===========================================================================

_RANK_MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}


@router.callback_query(F.data == "nav_leaderboard")
async def cb_nav_leaderboard(query: CallbackQuery) -> None:
    if not query.message or not hasattr(query.message, "edit_text"):
        await query.answer()
        return
    await query.answer()

    top_users = await get_leaderboard(limit=10)

    if not top_users:
        await query.message.edit_text(
            "🏆 <b>Leaderboard abhi khali hai.</b>\n\n"
            "Missions complete karo aur pehle ban jao! 🚀",
            reply_markup=leaderboard_keyboard(),
        )
        return

    lines: list[str] = [
        "━━━━━━━━━━━━━━━━━━━━━━━",
        "🏆 <b>LIFETIME LEADERBOARD</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    for i, user in enumerate(top_users, start=1):
        medal = _RANK_MEDALS.get(i, f"{i}.")
        raw_name = user.get("first_name") or "Anonymous"
        name = html.escape(raw_name)
        sparks = int(user.get("lifetime_sparks", 0))
        lines.append(f"{medal} {name} — <b>{sparks:,} ⚡</b>")

    lines += ["", "━━━━━━━━━━━━━━━━━━━━━━━"]

    await query.message.edit_text(
        "\n".join(lines),
        reply_markup=leaderboard_keyboard(),
    )


# ===========================================================================
# /help
# ===========================================================================


@router.message(Command("help"))
@router.message(F.text == "❓ Help")
async def cmd_help(message: Message) -> None:
    await message.answer(
        "❓ <b>InstaVault Help Center</b>\n\n"
        "⚡ <b>Sparks</b> — Virtual currency. Earn by doing missions.\n"
        "🎯 <b>Mission</b> — 1 daily mission.\n"
        "📦 <b>Order</b> — Spend Sparks to get real Instagram views.\n"
        "👥 <b>Refer</b> — Share your link; earn Sparks for every friend.\n\n"
        "<i>Need more help? Tap the button below.</i>",
        reply_markup=help_keyboard(),
    )


# ===========================================================================
# SCREEN 8 — 📦 Order History
# ===========================================================================

_STATUS_DISPLAY = {
    "pending": "⏳ Pending",
    "delivered": "✅ Delivered",
    "cancelled": "❌ Cancelled",
}

_PKG_NAMES = {
    "starter": "🌱 Starter Boost",
    "growth": "🔥 Growth Pack",
    "pro": "💎 Pro Blast",
    "mega": "⚡ Mega",
}

_HISTORY_PAGE_SIZE = 3


async def _render_order_history(
    user_id: int,
    message: Message,
    edit: bool,
    page: int = 0,
) -> None:
    """Fetch and render paginated order history for a user."""

    # 1. Get total orders dynamically from the user's profile
    user_data = await get_user(user_id)
    if not user_data:
        return

    total = user_data.get("total_orders", 0)

    if total == 0:
        text = (
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "📦 <b>ORDER HISTORY</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "😅 <b>Abhi tak koi order nahi kiya!</b>\n\n"
            "Sparks kamao aur apna pehla order dalo. 🚀\n"
            "━━━━━━━━━━━━━━━━━━━━━━━"
        )
        kb = order_history_keyboard()
        if edit:
            await message.edit_text(text, reply_markup=kb)
        else:
            await message.answer(text, reply_markup=kb)
        return

    total_pages = max(1, (total + _HISTORY_PAGE_SIZE - 1) // _HISTORY_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))

    # 2. Fetch ONLY the specific page from the database (Server-side pagination)
    page_orders = await get_user_orders(user_id, limit=_HISTORY_PAGE_SIZE, page=page)

    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━━",
        "📦 <b>ORDER HISTORY</b>",
        f"<i>Page {page + 1}/{total_pages}  •  Total: {total} orders</i>",
        "━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    for i, order in enumerate(page_orders, start=page * _HISTORY_PAGE_SIZE + 1):
        order_id = order.get("order_id", "—")
        pkg = _PKG_NAMES.get(
            order.get("package_type", ""), order.get("package_type", "—").title()
        )
        views = int(order.get("views_ordered", 0))
        sparks = int(order.get("sparks_spent", 0))
        ig = order.get("instagram_url") or "—"
        status = _STATUS_DISPLAY.get(order.get("status", "pending"), "🔄 Processing")
        created = format_timestamp(order.get("created_at"), fmt="%d %b %Y, %I:%M %p")

        lines += [
            "",
            f"<b>Order #{i}  —  {pkg}</b>",
            f"🆔 ID: <code>{order_id[:12]}…</code>",
            f"📅 {created} IST",
            f"👁 Views: <b>{views:,}</b>   ⚡ Cost: <b>{sparks:,} Sparks</b>",
            f"📸 IG Handle: @{ig}",
            f"📊 Status: {status}",
        ]

    lines.append("\n━━━━━━━━━━━━━━━━━━━━━━━")
    text = "\n".join(lines)

    kb = order_history_keyboard(
        has_prev=(page > 0),
        has_next=(page < total_pages - 1),
        page=page,
    )

    if edit:
        await message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "nav_order_history")
async def cb_nav_order_history(query: CallbackQuery) -> None:
    if not query.message or not hasattr(query.message, "edit_text"):
        await query.answer()
        return
    await query.answer()
    await _render_order_history(query.from_user.id, query.message, edit=True, page=0)


@router.callback_query(F.data.startswith("order_history_page:"))
async def cb_order_history_page(query: CallbackQuery) -> None:
    if not query.message or not hasattr(query.message, "edit_text"):
        await query.answer()
        return
    await query.answer()
    try:
        page = int(query.data.split(":")[1])
    except (IndexError, ValueError):
        page = 0
    await _render_order_history(query.from_user.id, query.message, edit=True, page=page)


# ===========================================================================
# User Transaction History — Shared Service
# ---------------------------------------------------------------------------
# Uses the shared ``services.transaction_history`` module for rendering.
# User-specific: user_id is taken from ``query.from_user.id``, and the
# back button returns to the Profile screen.
#
# Callbacks handled:
#   nav_my_transactions     — entry point from profile keyboard
#   my_tx_page:{page}       — pagination (prev/next navigation)
# ===========================================================================

from instavault.services.transaction_history import (
    render_transaction_page,
    build_transaction_keyboard,
)


@router.callback_query(F.data == "nav_my_transactions")
async def cb_my_transactions(query: CallbackQuery) -> None:
    """Show the logged-in user's transaction history (page 0)."""
    if not query.message or not hasattr(query.message, "edit_text"):
        await query.answer()
        return
    await query.answer()

    uid = query.from_user.id
    text, _total, total_pages = await render_transaction_page(uid, page=0)
    kb = build_transaction_keyboard(
        user_id=uid,
        page=0,
        total_pages=total_pages,
        back_callback="nav_profile",
        callback_prefix="my_tx_page",
    )
    await query.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data.startswith("my_tx_page:"))
async def cb_my_tx_page(query: CallbackQuery) -> None:
    """Pagination: navigate between the user's transaction history pages."""
    if not query.message or not hasattr(query.message, "edit_text"):
        await query.answer()
        return
    await query.answer()

    uid = query.from_user.id
    # my_tx_page:{page}
    try:
        page = int(query.data.split(":")[1])
    except (IndexError, ValueError):
        page = 0

    text, _total, total_pages = await render_transaction_page(uid, page=page)
    kb = build_transaction_keyboard(
        user_id=uid,
        page=page,
        total_pages=total_pages,
        back_callback="nav_profile",
        callback_prefix="my_tx_page",
    )
    await query.message.edit_text(text, reply_markup=kb)


# ===========================================================================
# Placeholder / Coming-Soon callbacks (anti-crash protocol)
# ===========================================================================

_COMING_SOON = {
    "contact_support",
    "faq",
}


@router.callback_query(F.data.in_(_COMING_SOON))
async def cb_coming_soon(query: CallbackQuery) -> None:
    if not query.message or not hasattr(query.message, "edit_text"):
        await query.answer()
        return
    await query.answer(
        "🚧 This feature is currently under development and will be available in the next update!",
        show_alert=True,
    )


@router.callback_query(F.data == "action_download_apk")
async def cb_action_download_apk(query: CallbackQuery) -> None:
    """Send the APK to the user when they click the download button."""
    if not query.message or not hasattr(query.message, "edit_text"):
        await query.answer()
        return

    await query.answer("⏳ Fetching the latest version for you...", show_alert=False)

    if not config.APK_FILE_ID:
        await query.message.answer(
            "🚧 Server is updating the APK. Please try again in a few hours."
        )
        return

    caption = (
        "📱 <b>InstaVault Application (Latest)</b>\n\n"
        "✨ Enjoy a seamless and robust experience!\n"
        "🔒 Secure, Fast, and Reliable.\n\n"
        "Download and install the APK below 👇"
    )

    try:
        await query.message.answer_document(
            document=config.APK_FILE_ID,
            caption=caption,
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error("Failed to send APK to user %s: %s", query.from_user.id, e)
        await query.message.answer(
            "🚧 System is busy syncing the file. Please try again in a few minutes."
        )


# ===========================================================================
# PHASE 6 — Instagram Handle Linking (FSM)
# ===========================================================================


@router.callback_query(F.data == "action_link_ig")
async def cb_action_link_ig(query: CallbackQuery, state: FSMContext) -> None:
    if not query.message or not hasattr(query.message, "edit_text"):
        await query.answer()
        return
    """Enter FSM: prompt the user to send their Instagram handle or URL."""
    await query.answer()

    await state.set_state(ProfileState.waiting_for_ig_handle)

    await query.message.edit_text(
        "📸 <b>Instagram Handle Link Karo</b>\n\n"
        "Apna Instagram username ya profile link bhejo.\n\n"
        "<i>Example:</i>\n"
        "• <code>achal_123</code>\n"
        "• <code>@achal_123</code>\n"
        "• <code>https://www.instagram.com/achal_123/</code>\n\n"
        "<i>(Cancel karne ke liye /cancel bhejein)</i>",
    )


@router.message(ProfileState.waiting_for_ig_handle)
async def handle_ig_input(message: Message, state: FSMContext) -> None:
    """Receive user input, clean it, save to Firestore, confirm."""
    if message.text is None:
        await message.answer("⚠️ Please send your Instagram username as text.")
        return

    raw = message.text.strip()

    # Cancel shortcut via text (besides /cancel command)
    if raw.lower() in ("/cancel", "cancel"):
        await state.clear()
        await message.answer(
            "❌ Instagram linking cancelled.",
            reply_markup=back_to_dashboard_keyboard(),
        )
        return

    # Block other bot commands from being captured as an IG handle
    if raw.startswith("/"):
        await message.answer(
            "⚠️ Please send your Instagram handle, not a command. Type /cancel to exit."
        )
        return

    cleaned = _clean_ig_handle(raw)

    if not cleaned:
        await message.answer(
            "⚠️ <b>Invalid username.</b> Please send a valid Instagram handle or profile link."
        )
        return

    user_id = message.from_user.id
    await update_user(user_id, {"instagram_handle": cleaned})
    await state.clear()

    logger.info("User %s linked Instagram handle: %s", user_id, cleaned)

    await message.answer(
        f"✅ <b>Tera Instagram handle (@{cleaned}) successfully link ho gaya hai</b> "
        f"aur database mein save ho chuka hai!",
        reply_markup=back_to_dashboard_keyboard(),
    )


@router.message(Command("cancel"), ProfileState.waiting_for_ig_handle)
async def cmd_cancel_link(message: Message, state: FSMContext) -> None:
    """/cancel command clears the IG linking FSM."""
    await state.clear()
    await message.answer(
        "❌ Instagram linking cancelled.",
        reply_markup=back_to_dashboard_keyboard(),
    )
