"""
handlers/games_hub.py
~~~~~~~~~~~~~~~~~~~~~
Routing and handlers for the Games & Earn feature.
Delegates ALL core logic to ``services/games_engine.py``.

Handlers:
  §1  nav_games_hub          — Main Games & Earn hub screen
  §2  game_coin_flip_menu    — Coin Flip: eligibility check → dice roll
  §3  game_quiz              — Quiz Trivia: 3 questions → claim via shortener
  §4  Coming Soon            — Placeholder for unreleased games
"""

from __future__ import annotations

import asyncio
import json
import logging

from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from instavault.core import config
from instavault.constants import rewards
from instavault.services.games_engine import (
    render_games_hub,
    check_coin_flip_eligibility,
    process_coin_flip_result,
    check_quiz_eligibility,
    check_answer,
    pick_quiz_questions,
    render_question,
    render_quiz_complete,
    QUIZ_NUM_QUESTIONS,
    QUIZ_REWARD_AMOUNT,
)
from instavault.services.mission_token import (
    create_quiz_token,
    get_pending_quiz_token,
    verify_and_consume_quiz,
    create_verify_token,
    get_pending_verify_token,
    verify_and_consume_verify,
)
from instavault.services.shortener_api import ShortenerApiError, create_short_link
from instavault.database.db_manager import complete_quiz_task, get_user, update_user
from instavault.keyboards.inline import games_hub_keyboard
from instavault.utils.helpers import get_ist_now

logger = logging.getLogger(__name__)
router = Router(name="games_hub")


# ===========================================================================
# §1  GAMES HUB — Entry Point
# ---------------------------------------------------------------------------
# Shown when user clicks "🎮 Games & Earn" in the Mission Center.
# Renders the hub welcome text + game selection keyboard.
# ===========================================================================


def _back_to_games_kb() -> InlineKeyboardMarkup:
    """Small keyboard with a single 'Back to Games Hub' button."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎮 Back to Games Hub",
                    callback_data="nav_games_hub",
                ),
            ],
        ]
    )


# ---------------------------------------------------------------------------
# §0b  VERIFY HUMAN — Shortener gate for daily-limit cooldown
# ---------------------------------------------------------------------------
# When user hits daily limit on any game, we don't directly say "limit".
# Instead we show "We think you might not be human — verify first".
# After user clicks the shortener link (views ads) and returns via
# deep-link, THEN we show the actual daily limit message.
# ---------------------------------------------------------------------------


async def _show_verify_human_screen(query: CallbackQuery) -> None:
    """Generate shortener link and show 'Verify You're Human' screen.

    Called when user tries to play a game that has daily limit reached.
    If user already verified today (from ANY source — 500 Sparks shortener,
    vf_ cooldown verify, etc.), skip the verify screen and show direct
    'Day Limit Reached' message instead.
    """
    user_id = query.from_user.id

    # ── Already verified today? Skip verify, show direct limit msg ────
    user_data = await get_user(user_id)
    today_str = get_ist_now().date().strftime("%Y-%m-%d")
    if user_data and user_data.get("last_shortener_task_date") == today_str:
        await query.message.edit_text(
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "⏳ <b>DAILY LIMIT REACHED!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "✅ Aaj ka human verification ho chuka hai.\n"
            "Aaj ke saare game tries bhi khatam ho chuke hain.\n\n"
            "Kal wapas aana naye games ke liye! 🌅\n\n"
            "<i>Resets daily at midnight IST.</i>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━",
            reply_markup=_back_to_games_kb(),
        )
        return

    # ── Not yet verified — show verify screen with shortener link ─────
    bot_username = config.BOT_USERNAME or "InstaVaultBot"

    # Check for existing pending token
    pending_token = await get_pending_verify_token(user_id)

    if not pending_token:
        pending_token = await create_verify_token(user_id)

    deep_link_url = f"https://t.me/{bot_username}?start={pending_token}"

    try:
        short_url = await create_short_link(deep_link_url)
    except ShortenerApiError as e:
        logger.error("GPLinks failed for verify user %s: %s", user_id, e)
        # Fallback: show direct cooldown message if GPLinks fails
        await query.message.edit_text(
            "⏳ <b>Daily Limit Reached!</b>\n\n"
            "Aaj ke saare tries khatam ho gaye.\n"
            "Kal wapas aana naye games ke liye! 🌅",
            reply_markup=_back_to_games_kb(),
        )
        return

    await query.message.edit_text(
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🤖 <b>VERIFY YOU'RE HUMAN</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🔒 Hume lagta hai aap human nahi ho.\n"
        "Neeche button pe click karke verify karo!\n\n"
        "📋 <b>Kya karna hai:</b>\n"
        "→ Neeche button par click karo\n"
        "→ Page load hone do aur complete karo\n"
        "→ Automatic wapas bot pe aa jaoge\n"
        "━━━━━━━━━━━━━━━━━━━━━━━",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔗 Verify You're Human",
                        url=short_url,
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="🎮 Back to Games Hub",
                        callback_data="nav_games_hub",
                    ),
                ],
            ]
        ),
    )


@router.callback_query(F.data == "nav_games_hub")
async def cb_nav_games_hub(query: CallbackQuery) -> None:
    """Entry point: show the Games & Earn hub with available games."""
    if not query.message or not hasattr(query.message, "edit_text"):
        await query.answer()
        return
    await query.answer()

    user_id = query.from_user.id
    first_name = query.from_user.first_name or "Player"

    # ── Check if user already verified today ──────────────────────────
    user_data = await get_user(user_id)
    today_str = get_ist_now().date().strftime("%Y-%m-%d")
    verified_today = (
        user_data is not None
        and user_data.get("last_shortener_task_date") == today_str
    )

    # Service renders the text — no hardcoded strings here
    text = await render_games_hub(user_id, first_name, verified_today=verified_today)
    kb = games_hub_keyboard(verified_today=verified_today)

    await query.message.edit_text(text, reply_markup=kb)


# ===========================================================================
# §2  COIN FLIP — Free Daily Dice Roll
# ---------------------------------------------------------------------------
# Flow:
#   1. User clicks "🎲 Coin Flip" → handler checks eligibility via service
#   2. If cooldown active → show cooldown message with Back button
#   3. If eligible → send Telegram 🎲 dice animation
#   4. Wait for dice animation to complete (~4 seconds)
#   5. Extract dice value → call service to process reward
#   6. Show result card with earned Sparks
#
# The Telegram dice animation returns a random 1–6 value server-side.
# We cannot manipulate this — it's Telegram's true RNG.
# ===========================================================================


@router.callback_query(F.data == "game_coin_flip_menu")
async def cb_coin_flip(query: CallbackQuery) -> None:
    """Handle Coin Flip: check eligibility → roll dice → grant reward."""
    if not query.message:
        await query.answer()
        return
    await query.answer()

    user_id = query.from_user.id
    chat_id = query.message.chat.id

    # ── 1. Eligibility check (service layer) ──────────────────────────────
    is_eligible, msg = await check_coin_flip_eligibility(user_id)

    if not is_eligible:
        # Cooldown active — show "Verify You're Human" instead of direct limit msg
        await _show_verify_human_screen(query)
        return

    # ── 2. Send rolling message ───────────────────────────────────────────
    await query.message.edit_text(
        "🎲 <b>COIN FLIP</b>\n\n"
        "Rolling the dice... 🎲\n\n"
        "<i>Result × 10 = Your free Sparks!</i>"
    )

    # ── 3. Send Telegram dice animation (true RNG) ────────────────────────
    dice_msg = await query.message.answer_dice(emoji="🎲")
    dice_value = dice_msg.dice.value  # 1–6 from Telegram server

    # ── 4. Wait for dice animation to complete (~4 sec) ───────────────────
    await asyncio.sleep(4)

    # ── 5. Process result via service layer ───────────────────────────────
    reward, result_text = await process_coin_flip_result(user_id, dice_value)

    logger.info(
        "Coin Flip — user=%s dice=%d reward=%d",
        user_id,
        dice_value,
        reward,
    )

    # ── 6. Show result card ───────────────────────────────────────────────
    await query.message.answer(result_text, reply_markup=_back_to_games_kb())


# ===========================================================================
# §3  QUIZ TRIVIA — Answer 3 Questions → Claim via Shortener Verification
# ---------------------------------------------------------------------------
# Flow:
#   1. game_quiz            → eligibility check → show Q1
#   2. quiz_ans:{qi}:{ai}   → verify answer → correct: next Q / wrong: retry
#   3. After Q3 correct     → "🎉 Claim 250 Sparks" button
#   4. quiz_claim           → generate shortener link (verify human)
#   5. User visits link     → returns via /start qz_xxx deep-link
#   6. handle_quiz_deeplink → verify token → grant 250 Sparks
#
# State is encoded in callback data (no FSM needed):
#   quiz_ans:{question_index}:{answer_index}
#   Questions are sent as JSON in the callback to avoid DB lookups.
#
# Since we store question indices in callback data, the quiz session
# is stateless — no FSM, no Redis state tracking needed.
# We track the list of question indices across callbacks.
# ===========================================================================


# ── In-memory quiz sessions ───────────────────────────────────────────────
# Stores the current quiz session's questions for each user.
# Key: user_id, Value: list of question dicts
# Cleared after quiz completion or new session start.
_quiz_sessions: dict[int, list[dict]] = {}


def _build_answer_keyboard(question: dict, question_index: int) -> InlineKeyboardMarkup:
    """Build inline keyboard with 4 answer options for a quiz question.

    Each button's callback data encodes the question index and answer index:
        quiz_ans:{question_index}:{answer_index}
    """
    options = question["options"]
    labels = ["🅰️", "🅱️", "🅲️", "🅳️"]

    rows: list[list[InlineKeyboardButton]] = []
    for i, option in enumerate(options):
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{labels[i]} {option}",
                    callback_data=f"quiz_ans:{question_index}:{i}",
                )
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "game_quiz")
async def cb_quiz_start(query: CallbackQuery) -> None:
    """Start the Quiz Trivia: check eligibility → show Question 1."""
    if not query.message or not hasattr(query.message, "edit_text"):
        await query.answer()
        return
    await query.answer()

    user_id = query.from_user.id

    # ── 1. Eligibility check ──────────────────────────────────────────────
    is_eligible, msg = await check_quiz_eligibility(user_id)

    if not is_eligible:
        # Cooldown active — show "Verify You're Human" instead of direct limit msg
        await _show_verify_human_screen(query)
        return

    # ── 2. Pick 3 random questions and store in session ───────────────────
    questions = pick_quiz_questions()
    _quiz_sessions[user_id] = questions

    # ── 3. Show Question 1 ────────────────────────────────────────────────
    q = questions[0]
    text = render_question(q, question_number=1)
    kb = _build_answer_keyboard(q, question_index=0)

    await query.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data.startswith("quiz_ans:"))
async def cb_quiz_answer(query: CallbackQuery) -> None:
    """Handle a quiz answer: check correct → next question or complete."""
    if not query.message or not hasattr(query.message, "edit_text"):
        await query.answer()
        return

    user_id = query.from_user.id

    # ── Parse callback data ───────────────────────────────────────────────
    # quiz_ans:{question_index}:{answer_index}
    parts = query.data.split(":")
    try:
        q_index = int(parts[1])
        a_index = int(parts[2])
    except (IndexError, ValueError):
        await query.answer("❌ Invalid answer.", show_alert=True)
        return

    # ── Get session questions ─────────────────────────────────────────────
    questions = _quiz_sessions.get(user_id)
    if not questions or q_index >= len(questions):
        await query.answer(
            "⚠️ Quiz session expired. Please start a new quiz.",
            show_alert=True,
        )
        return

    question = questions[q_index]

    # ── Check answer via service ──────────────────────────────────────────
    is_correct = check_answer(question, a_index)

    if not is_correct:
        # Wrong answer — show alert and let them try again
        correct_option = question["options"][question["answer"]]
        await query.answer(
            f"❌ Wrong! Correct answer: {correct_option}. Try again!",
            show_alert=True,
        )
        return

    # ── Correct answer! ───────────────────────────────────────────────────
    await query.answer("✅ Correct!", show_alert=False)

    next_q_index = q_index + 1

    if next_q_index < len(questions):
        # ── Show next question ────────────────────────────────────────────
        next_q = questions[next_q_index]
        text = render_question(next_q, question_number=next_q_index + 1)
        kb = _build_answer_keyboard(next_q, question_index=next_q_index)
        await query.message.edit_text(text, reply_markup=kb)
    else:
        # ── All 3 questions answered correctly → show claim screen ────────
        text = render_quiz_complete()
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🎁 Claim 250 Sparks",
                        callback_data="quiz_claim",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="🎮 Back to Games Hub",
                        callback_data="nav_games_hub",
                    ),
                ],
            ]
        )
        await query.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data == "quiz_claim")
async def cb_quiz_claim(query: CallbackQuery) -> None:
    """Claim quiz reward: generate shortener link for human verification."""
    if not query.message or not hasattr(query.message, "edit_text"):
        await query.answer()
        return
    await query.answer()

    user_id = query.from_user.id

    # ── Double-check: quiz not already completed today ────────────────────
    user_data = await get_user(user_id)
    today_str = get_ist_now().strftime("%Y-%m-%d")
    if user_data and user_data.get("last_quiz_date") == today_str:
        await query.message.edit_text(
            "✅ Aaj ka Quiz pehle hi complete ho chuka hai!",
            reply_markup=_back_to_games_kb(),
        )
        return

    # ── Check for existing pending token (prevent duplicate generation) ───
    bot_username = config.BOT_USERNAME or "InstaVaultBot"
    pending_token = await get_pending_quiz_token(user_id)

    if pending_token:
        # Re-use existing token
        deep_link_url = f"https://t.me/{bot_username}?start={pending_token}"
        try:
            short_url = await create_short_link(deep_link_url)
        except ShortenerApiError as e:
            logger.error("GPLinks retry failed for quiz user %s: %s", user_id, e)
            await query.message.edit_text(
                "⚠️ Link generate karne mein error aaya. Thodi der baad try karein.",
                reply_markup=_back_to_games_kb(),
            )
            return

        await _show_quiz_verify_screen(query, short_url)
        return

    # ── Generate new token + short link ───────────────────────────────────
    token = await create_quiz_token(user_id)
    deep_link_url = f"https://t.me/{bot_username}?start={token}"

    try:
        short_url = await create_short_link(deep_link_url)
    except ShortenerApiError as e:
        logger.error("GPLinks failed for quiz user %s: %s", user_id, e)
        await query.message.edit_text(
            "⚠️ Link generate karne mein error aaya. Thodi der baad try karein.",
            reply_markup=_back_to_games_kb(),
        )
        return

    await _show_quiz_verify_screen(query, short_url)

    # Clean up session memory
    _quiz_sessions.pop(user_id, None)


async def _show_quiz_verify_screen(query: CallbackQuery, short_url: str) -> None:
    """Render the 'Verify You're Human' screen with the GPLinks button."""
    reward = QUIZ_REWARD_AMOUNT
    await query.message.edit_text(
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔒 <b>VERIFY YOU'RE HUMAN</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🪙 <b>Reward:</b> {reward} Sparks\n"
        "⏰ <b>Time Limit:</b> 30 minutes\n\n"
        "📋 <b>Kya karna hai:</b>\n"
        "→ Neeche button par click karo\n"
        "→ Page load hone do aur complete karo\n"
        "→ Automatic wapas bot pe aa jaoge\n"
        "→ Sparks credit ho jayenge! ⚡\n"
        "━━━━━━━━━━━━━━━━━━━━━━━",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔗 Verify & Claim Sparks",
                        url=short_url,
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="🎮 Back to Games Hub",
                        callback_data="nav_games_hub",
                    ),
                ],
            ]
        ),
    )


# ===========================================================================
# §3b  QUIZ DEEP-LINK RETURN — /start qz_xxx
# ---------------------------------------------------------------------------
# Called from handlers/start.py when a returning user's deep-link
# starts with the "qz_" prefix. Verifies the token and grants reward.
# ===========================================================================


async def handle_quiz_deeplink(message: Message, user_id: int, token: str) -> None:
    """Verify quiz token, check daily limit, credit reward.

    Args:
        message: The /start message that triggered the deep-link.
        user_id: The Telegram user ID of the claimant.
        token: The full token string (e.g. "qz_abc123def456").
    """
    is_valid = await verify_and_consume_quiz(token, user_id)

    if not is_valid:
        await message.answer(
            "⚠️ <b>Invalid or Expired Verification Link</b>\n\n"
            "Yeh link expire ho chuka hai ya pehle se use ho chuka hai.\n"
            "Games Hub se naya quiz start karein.",
            reply_markup=_back_to_games_kb(),
        )
        return

    # Double-check: quiz not already completed today
    user_data = await get_user(user_id)
    today_str = get_ist_now().strftime("%Y-%m-%d")
    if user_data and user_data.get("last_quiz_date") == today_str:
        await message.answer(
            "✅ Aaj ka Quiz pehle hi complete ho chuka hai!",
            reply_markup=_back_to_games_kb(),
        )
        return

    # Credit reward atomically
    reward = rewards.QUIZ_REWARD
    try:
        await complete_quiz_task(user_id, reward)
    except Exception as e:
        logger.error(
            "Failed to credit quiz reward for user %s: %s",
            user_id,
            e,
            exc_info=True,
        )
        await message.answer(
            "⚠️ Verification successful lekin reward credit mein error aaya.\n"
            "Kripya admin se contact karein.",
            reply_markup=_back_to_games_kb(),
        )
        return

    await message.answer(
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🎉 <b>QUIZ REWARD CLAIMED!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⚡ <b>+{reward} Sparks</b> aapke account mein add ho gaye!\n\n"
        "Kal naye quiz ke liye wapas aana! 🧠\n"
        "━━━━━━━━━━━━━━━━━━━━━━━",
        reply_markup=_back_to_games_kb(),
    )


# ===========================================================================
# §3c  VERIFY DEEP-LINK RETURN — /start vf_xxx
# ---------------------------------------------------------------------------
# Called from handlers/start.py when a returning user's deep-link
# starts with the "vf_" prefix. Verifies the token and shows
# the actual daily limit message. No reward is granted.
# ===========================================================================


async def handle_verify_deeplink(
    message: Message, user_id: int, token: str
) -> None:
    """Verify human token, then show the daily limit message.

    Args:
        message: The /start message that triggered the deep-link.
        user_id: The Telegram user ID.
        token: The full token string (e.g. "vf_abc123def456").
    """
    is_valid = await verify_and_consume_verify(token, user_id)

    if not is_valid:
        await message.answer(
            "⚠️ <b>Invalid or Expired Verification Link</b>\n\n"
            "Yeh link expire ho chuka hai ya pehle se use ho chuka hai.",
            reply_markup=_back_to_games_kb(),
        )
        return

    # Verification successful — mark as verified today so all verify
    # buttons disappear (same field used by 500 Sparks shortener)
    today_str = get_ist_now().date().strftime("%Y-%m-%d")
    await update_user(user_id, {"last_shortener_task_date": today_str})

    # Show daily limit message
    await message.answer(
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "✅ <b>VERIFICATION SUCCESSFUL!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🤖→👤 Human verified!\n\n"
        "⏳ <b>Daily Limit Reached</b>\n"
        "Aaj ke saare game tries khatam ho chuke hain.\n"
        "Kal wapas aana naye games ke liye! 🌅\n\n"
        "<i>Resets daily at midnight IST.</i>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━",
        reply_markup=_back_to_games_kb(),
    )


# ===========================================================================
# §4  COMING SOON PLACEHOLDERS
# ---------------------------------------------------------------------------
# Handles clicks on games that are not yet implemented.
# Shows a Telegram alert popup — prevents "unhandled callback" errors.
#
# Coming Soon games:
#   🎰 Daily Spin — game_daily_spin
# ===========================================================================

_GAMES_COMING_SOON = {"game_daily_spin"}


@router.callback_query(F.data.in_(_GAMES_COMING_SOON))
async def cb_game_coming_soon(query: CallbackQuery) -> None:
    """Show 'coming soon' alert for games still under development."""
    await query.answer(
        "🚧 ⚔️ Bot Battle Arena (3 Rounds vs Bot) under development hai. Bahut jald aayega! Stay tuned! 🔥",
        show_alert=True,
    )
