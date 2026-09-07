"""
handlers/tasks_shortener.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Shortlink Mission — GPLinks-based daily earning task.

Two entry points:
  1. Callback 'task_shortener_start' → Check eligibility → Generate link
  2. Deep-link /start sl_xxx → Verify token → Credit reward

This is ONE of potentially many mission types. Each mission type
has its own handler file (tasks_*.py), its own DB date field,
and its own token prefix — so they never interfere with each other.

Architecture:
  - Token lifecycle managed by services/mission_token.py (Redis)
  - Short link generation by services/shortener_api.py (GPLinks)
  - Reward credit by database/db_manager.complete_shortener_task (Firestore)
"""

import logging

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from instavault.core import config
from instavault.database.db_manager import complete_shortener_task, get_user
from instavault.keyboards.inline import back_to_dashboard_keyboard
from instavault.services.mission_token import (
    create_token,
    get_pending_token,
    verify_and_consume,
)
from instavault.services.shortener_api import ShortenerApiError, create_short_link
from instavault.utils.helpers import get_ist_now
from instavault.constants import rewards

logger = logging.getLogger(__name__)
router = Router(name="tasks_shortener")


# ---------------------------------------------------------------------------
# Inline keyboard helpers (private to this handler)
# ---------------------------------------------------------------------------


def _mission_link_keyboard(short_url: str) -> InlineKeyboardMarkup:
    """Inline keyboard with the Captcha Verification URL button."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🛡️ Click Here to Verify (Captcha)",
                    url=short_url,
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


# ===========================================================================
# ENTRY POINT 1 — User clicks "🛡️ Verify You Are Human" in Mission Center
# ===========================================================================


@router.callback_query(F.data == "task_shortener_start")
async def cb_shortener_task(query: CallbackQuery) -> None:
    """Check eligibility, generate token + GPLinks short URL, show to user."""
    if not query.message or not hasattr(query.message, "edit_text"):
        await query.answer()
        return
    await query.answer()

    user_id = query.from_user.id
    user_data = await get_user(user_id)
    if not user_data:
        await query.message.edit_text(
            "⚠️ Please /start first.",
            reply_markup=back_to_dashboard_keyboard(),
        )
        return

    # ── Check if shortener task already completed today ────────────────
    today_str = get_ist_now().strftime("%Y-%m-%d")
    if user_data.get("last_shortener_task_date") == today_str:
        await query.message.edit_text(
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "✅ <b>VERIFICATION COMPLETED!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🎉 Aaj ka Human Verification (Captcha) aap pehle hi complete kar chuke hain.\n"
            "Kal naye verification aur Sparks ke liye wapas aana! 🌅\n"
            "━━━━━━━━━━━━━━━━━━━━━━━",
            reply_markup=back_to_dashboard_keyboard(),
        )
        return

    # ── Check for existing pending token (prevent duplicate generation) ─
    bot_username = config.BOT_USERNAME or "InstaVaultBot"
    pending_token = await get_pending_token(user_id)

    if pending_token:
        # User already has a pending token — re-generate the short link
        deep_link_url = f"https://t.me/{bot_username}?start={pending_token}"
        try:
            short_url = await create_short_link(deep_link_url)
        except ShortenerApiError as e:
            logger.error("GPLinks retry failed for user %s: %s", user_id, e)
            await query.message.edit_text(
                "⚠️ Link generate karne mein error aaya. Thodi der baad try karein.",
                reply_markup=back_to_dashboard_keyboard(),
            )
            return

        await _show_mission_screen(query, short_url)
        return

    # ── Generate new token + short link ────────────────────────────────
    token = await create_token(user_id)
    deep_link_url = f"https://t.me/{bot_username}?start={token}"

    try:
        short_url = await create_short_link(deep_link_url)
    except ShortenerApiError as e:
        logger.error("GPLinks failed for user %s: %s", user_id, e)
        await query.message.edit_text(
            "⚠️ Link generate karne mein error aaya. Thodi der baad try karein.",
            reply_markup=back_to_dashboard_keyboard(),
        )
        return

    await _show_mission_screen(query, short_url)


async def _show_mission_screen(query: CallbackQuery, short_url: str) -> None:
    """Render the human verification captcha screen with the verification button."""
    reward = rewards.SHORTENER_TASK_REWARD
    await query.message.edit_text(
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🛡️ <b>HUMAN VERIFICATION (CAPTCHA)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Bot security aur anti-cheat check ke liye human verification zaroori hai.\n"
        "Quick verification complete karein aur instant reward payein!\n\n"
        f"🪙 <b>Verification Reward:</b> {reward} Sparks\n"
        "⏰ <b>Validity:</b> 30 minutes\n\n"
        "📋 <b>Verification Steps:</b>\n"
        "1️⃣ Neeche <b>'🛡️ Click Here to Verify (Captcha)'</b> par click karo\n"
        "2️⃣ Browser mein Captcha verification complete karo\n"
        "3️⃣ Verification hote hi automatic bot par redirect ho jaoge\n"
        f"4️⃣ Account mein <b>+{reward} Sparks</b> jud jayenge! ⚡\n"
        "━━━━━━━━━━━━━━━━━━━━━━━",
        reply_markup=_mission_link_keyboard(short_url),
    )


# ===========================================================================
# ENTRY POINT 2 — Deep-link return: /start sl_xxx
# Called from handlers/start.py when a returning user's deep-link
# starts with the "sl_" prefix.
# ===========================================================================


async def handle_shortener_deeplink(message: Message, user_id: int, token: str) -> None:
    """Verify token, check daily limit, credit reward.

    Args:
        message: The /start message that triggered the deep-link.
        user_id: The Telegram user ID of the claimant.
        token: The full token string (e.g. "sl_abc123def456").
    """
    is_valid = await verify_and_consume(token, user_id)

    if not is_valid:
        await message.answer(
            "⚠️ <b>Invalid or Expired Verification Link</b>\n\n"
            "Yeh verification link expire ho chuka hai ya pehle se use ho chuka hai.\n"
            "Mission Center se dobara verification link generate karein.",
            reply_markup=back_to_dashboard_keyboard(),
        )
        return

    # Double-check: task not already completed today
    # (belt-and-suspenders safety alongside Redis token atomicity)
    user_data = await get_user(user_id)
    today_str = get_ist_now().strftime("%Y-%m-%d")
    if user_data and user_data.get("last_shortener_task_date") == today_str:
        await message.answer(
            "✅ Aaj ka Human Verification pehle hi complete ho chuka hai!",
            reply_markup=back_to_dashboard_keyboard(),
        )
        return

    # Credit reward atomically
    reward = rewards.SHORTENER_TASK_REWARD
    try:
        await complete_shortener_task(user_id, reward)
    except Exception as e:
        logger.error(
            "Failed to credit shortener reward for user %s: %s",
            user_id,
            e,
            exc_info=True,
        )
        await message.answer(
            "⚠️ Verification verify ho gaya lekin reward credit mein error aaya.\n"
            "Kripya admin se contact karein.",
            reply_markup=back_to_dashboard_keyboard(),
        )
        return

    await message.answer(
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🎉 <b>VERIFICATION SUCCESSFUL!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "✅ Aapka Human Verification successfully verify ho gaya!\n"
        f"⚡ <b>+{reward} Sparks</b> aapke account mein add ho gaye!\n\n"
        "Ab aap Instagram Views order kar sakte hain. 🚀\n"
        "Kal dobara verification karke aur Sparks kama sakte hain!\n"
        "━━━━━━━━━━━━━━━━━━━━━━━",
        reply_markup=back_to_dashboard_keyboard(),
    )
