"""
services/games_engine.py
~~~~~~~~~~~~~~~~~~~~~~~~
Core service logic for the Games & Earn feature.

Architecture:
  • Pure service layer — no routers, no callback handlers, no FSM.
  • All game logic, eligibility checks, reward calculations, and
    result rendering live here.
  • Handlers in ``handlers/games_hub.py`` only call these functions
    and send the Telegram dice animation — zero hardcoded logic.

Games:
  🎲 Coin Flip   — Free daily dice roll. Reward = dice_value × 10 Sparks.
                    1 flip per day per user. Cooldown tracked via
                    ``last_coin_flip_date`` field in user document.
  🧠 Quiz Trivia — Answer 3 questions → claim 250 Sparks via shortener
                    verification. 1 quiz per day. Cooldown tracked via
                    ``last_quiz_date`` field in user document.
  🎰 Daily Spin  — Coming Soon
"""

from __future__ import annotations

import logging
from datetime import date

from instavault.database.db_manager import (
    get_user,
    increment_spark_balance,
    log_transaction,
    update_user,
)
from instavault.utils.helpers import get_ist_now

logger = logging.getLogger(__name__)


# ===========================================================================
# §1  GAMES HUB — Main menu rendering
# ---------------------------------------------------------------------------
# Renders the welcome screen shown when user clicks "🎮 Games & Earn".
# Shows current balance and available games list.
# ===========================================================================


async def render_games_hub(user_id: int | str, first_name: str) -> str:
    """Fetch user data and render the Games & Earn hub message."""
    user_data = await get_user(user_id)
    if not user_data:
        return "⚠️ Profile not found. Please send /start."

    sparks = user_data.get("spark_balance", 0)

    text = (
        "🎮 <b>GAMES & EARN HUB</b>\n\n"
        f"👤 Player: <b>{first_name}</b>\n"
        f"🪙 Balance: <b>{sparks:,} Sparks</b>\n\n"
        "Welcome to the Arcade! Play mini-games to earn free Sparks daily.\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🕹️ <b>Available Games:</b>\n\n"
        "🎲 <b>Coin Flip</b>  •  <i>Free daily dice roll</i>\n"
        "   Roll the dice and earn <b>result × 10</b> Sparks!\n"
        "   🕐 Limit: 1 flip per day\n\n"
        "🧠 <b>Quiz Trivia</b>  •  <i>Answer & Earn</i>\n"
        "   Answer 3 questions → Claim <b>250 Sparks</b>!\n"
        "   🕐 Limit: 1 quiz per day\n\n"
        "🎰 <b>Daily Spin</b>  •  <i>Coming Soon</i>\n\n"
        "🛡️ <b>Human Verification</b>  •  <i>Anti-Bot Check</i>\n"
        "   Verify you are human → Claim <b>500 Sparks</b>!\n\n"
        "<i>Select an option below to start!</i>"
    )

    return text


# ===========================================================================
# §2  COIN FLIP — Core Game Logic
# ---------------------------------------------------------------------------
# Flow:
#   1. User clicks "🎲 Coin Flip" button
#   2. Handler calls ``check_coin_flip_eligibility()`` to verify cooldown
#   3. If eligible → handler sends Telegram dice animation (🎲 emoji)
#   4. Telegram returns dice result (1–6)
#   5. Handler calls ``process_coin_flip_result()`` with the dice value
#   6. Service grants reward = dice_value × 10 Sparks
#   7. Handler shows result card to user
#
# Cooldown:
#   Tracked via ``last_coin_flip_date`` field in user document.
#   Compared against current IST date (date only, not datetime).
#   Resets at midnight IST automatically.
#
# Reward Formula:
#   reward = dice_value × COIN_FLIP_MULTIPLIER
#   Dice 1 = 10 Sparks  →  Dice 6 = 60 Sparks
# ===========================================================================

# ── Constants ─────────────────────────────────────────────────────────────
COIN_FLIP_MULTIPLIER = 10  # dice_value × this = sparks earned


async def check_coin_flip_eligibility(user_id: int | str) -> tuple[bool, str]:
    """Check if a user is eligible for today's free Coin Flip.

    Args:
        user_id: Telegram user ID.

    Returns:
        A 2-tuple of ``(is_eligible, message)``.
        If not eligible, ``message`` explains why (cooldown active).
    """
    user_data = await get_user(user_id)
    if not user_data:
        return False, "⚠️ Profile not found. Please send /start first."

    # ── Cooldown check ────────────────────────────────────────────────────
    last_flip = user_data.get("last_coin_flip_date")
    today_ist = get_ist_now().date()

    if last_flip is not None:
        # Firestore stores datetime; extract date portion
        if hasattr(last_flip, "date"):
            last_flip_date = last_flip.date()
        elif isinstance(last_flip, date):
            last_flip_date = last_flip
        else:
            # Fallback: treat as string (should not happen)
            last_flip_date = None

        if last_flip_date == today_ist:
            return False, (
                "⏳ <b>Cooldown Active!</b>\n\n"
                "You've already used your free Coin Flip today.\n"
                "Come back tomorrow for another roll! 🎲\n\n"
                "<i>Resets daily at midnight IST.</i>"
            )

    return True, "✅ Eligible"


async def process_coin_flip_result(
    user_id: int | str, dice_value: int
) -> tuple[int, str]:
    """Process the Coin Flip result after Telegram dice animation.

    This function:
      1. Calculates the reward (dice_value × 10)
      2. Grants Sparks atomically via ``increment_spark_balance``
      3. Logs the transaction to the immutable ledger
      4. Updates the cooldown timestamp (``last_coin_flip_date``)
      5. Returns formatted result card text

    Args:
        user_id: Telegram user ID.
        dice_value: The dice result from Telegram (1–6).

    Returns:
        A 2-tuple of ``(reward_amount, result_message)``.
    """
    reward = dice_value * COIN_FLIP_MULTIPLIER

    # ── 1. Grant Sparks (atomic) ──────────────────────────────────────────
    await increment_spark_balance(user_id, reward)

    # ── 2. Log transaction (immutable ledger) ─────────────────────────────
    await log_transaction(
        user_id=user_id,
        tx_type="earn",
        amount=reward,
        source="game_coin_flip",
    )

    # ── 3. Update cooldown timestamp ──────────────────────────────────────
    await update_user(user_id, {"last_coin_flip_date": get_ist_now()})

    # ── 4. Fetch updated balance for display ──────────────────────────────
    updated_user = await get_user(user_id)
    new_balance = updated_user.get("spark_balance", 0) if updated_user else reward

    # ── 5. Build result card ──────────────────────────────────────────────
    # Emoji scale based on dice value
    if dice_value >= 5:
        reaction = "🔥 AMAZING ROLL!"
    elif dice_value >= 3:
        reaction = "✨ Nice roll!"
    else:
        reaction = "🍀 Better luck next time!"

    result_text = (
        "🎲 <b>COIN FLIP RESULT</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎯 You rolled: <b>{dice_value}</b>\n"
        f"💰 Reward: <b>+{reward} Sparks</b>  "
        f"({dice_value} × {COIN_FLIP_MULTIPLIER})\n\n"
        f"{reaction}\n\n"
        f"🪙 New Balance: <b>{new_balance:,} Sparks</b>\n\n"
        "<i>Come back tomorrow for another free roll!</i>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━"
    )

    return reward, result_text


# ===========================================================================
# §3  QUIZ TRIVIA — Answer 3 Questions → Claim via Shortener Verification
# ---------------------------------------------------------------------------
# Flow:
#   1. User clicks "🧠 Quiz" → handler checks daily eligibility
#   2. If eligible → show Question 1 with 4 options (inline buttons)
#   3. User answers → check correct → show Question 2 → ... → Question 3
#   4. After 3 correct answers → "🎉 Claim 250 Sparks" button
#   5. Claim button → generate shortener link (verify human)
#   6. User visits shortener link (views ads) → returns to bot via deep-link
#   7. Deep-link handler verifies token → grants 250 Sparks
#
# Question Bank:
#   20+ general knowledge questions. 3 random questions are picked per
#   quiz session. Questions rotate daily because selection is random.
#
# Cooldown:
#   Tracked via ``last_quiz_date`` field in user document.
#   Compared against current IST date string ("YYYY-MM-DD").
#   Resets at midnight IST automatically.
# ===========================================================================

import random

# ── Question Bank ─────────────────────────────────────────────────────────
# Each question is a dict: {"q": question_text, "options": [4 options], "answer": correct_index}
# answer is 0-indexed (0 = first option, 3 = last option)

QUIZ_QUESTIONS: list[dict] = [
    {
        "q": "What is the capital of India?",
        "options": ["Mumbai", "New Delhi", "Kolkata", "Chennai"],
        "answer": 1,
    },
    {
        "q": "Which planet is known as the Red Planet?",
        "options": ["Venus", "Jupiter", "Mars", "Saturn"],
        "answer": 2,
    },
    {
        "q": "How many continents are there on Earth?",
        "options": ["5", "6", "7", "8"],
        "answer": 2,
    },
    {
        "q": "What is the chemical symbol for water?",
        "options": ["O2", "CO2", "H2O", "NaCl"],
        "answer": 2,
    },
    {
        "q": "Who painted the Mona Lisa?",
        "options": ["Van Gogh", "Picasso", "Da Vinci", "Michelangelo"],
        "answer": 2,
    },
    {
        "q": "What is the largest ocean on Earth?",
        "options": ["Atlantic", "Indian", "Arctic", "Pacific"],
        "answer": 3,
    },
    {
        "q": "In which year did India gain independence?",
        "options": ["1945", "1947", "1950", "1942"],
        "answer": 1,
    },
    {
        "q": "What is the currency of Japan?",
        "options": ["Yuan", "Won", "Yen", "Ringgit"],
        "answer": 2,
    },
    {
        "q": "Which is the smallest country in the world?",
        "options": ["Monaco", "Vatican City", "San Marino", "Liechtenstein"],
        "answer": 1,
    },
    {
        "q": "How many bones are in the adult human body?",
        "options": ["196", "206", "216", "256"],
        "answer": 1,
    },
    {
        "q": "What does 'HTTP' stand for?",
        "options": [
            "HyperText Transfer Protocol",
            "High Tech Transfer Program",
            "Hyper Transfer Text Protocol",
            "Home Tool Transfer Protocol",
        ],
        "answer": 0,
    },
    {
        "q": "Which gas do plants absorb from the atmosphere?",
        "options": ["Oxygen", "Nitrogen", "Carbon Dioxide", "Hydrogen"],
        "answer": 2,
    },
    {
        "q": "What is the tallest mountain in the world?",
        "options": ["K2", "Kangchenjunga", "Lhotse", "Mount Everest"],
        "answer": 3,
    },
    {
        "q": "Which animal is known as the King of the Jungle?",
        "options": ["Tiger", "Elephant", "Lion", "Bear"],
        "answer": 2,
    },
    {
        "q": "How many days are in a leap year?",
        "options": ["364", "365", "366", "367"],
        "answer": 2,
    },
    {
        "q": "What is the national bird of India?",
        "options": ["Sparrow", "Parrot", "Eagle", "Peacock"],
        "answer": 3,
    },
    {
        "q": "Which company created the iPhone?",
        "options": ["Samsung", "Google", "Apple", "Microsoft"],
        "answer": 2,
    },
    {
        "q": "What is the speed of light?",
        "options": ["300,000 km/s", "150,000 km/s", "500,000 km/s", "100,000 km/s"],
        "answer": 0,
    },
    {
        "q": "Which is the longest river in the world?",
        "options": ["Amazon", "Yangtze", "Nile", "Mississippi"],
        "answer": 2,
    },
    {
        "q": "Who is the founder of Tesla?",
        "options": ["Jeff Bezos", "Bill Gates", "Elon Musk", "Mark Zuckerberg"],
        "answer": 2,
    },
]

QUIZ_NUM_QUESTIONS = 3  # questions per quiz session
QUIZ_REWARD_AMOUNT = 250  # Sparks for completing the quiz


def pick_quiz_questions() -> list[dict]:
    """Pick QUIZ_NUM_QUESTIONS random questions from the question bank.

    Returns a list of question dicts. Each session gets a fresh random set.
    """
    return random.sample(QUIZ_QUESTIONS, min(QUIZ_NUM_QUESTIONS, len(QUIZ_QUESTIONS)))


async def check_quiz_eligibility(user_id: int | str) -> tuple[bool, str]:
    """Check if a user is eligible for today's quiz.

    Args:
        user_id: Telegram user ID.

    Returns:
        A 2-tuple of ``(is_eligible, message)``.
        If not eligible, ``message`` explains why (cooldown active).
    """
    user_data = await get_user(user_id)
    if not user_data:
        return False, "⚠️ Profile not found. Please send /start first."

    # ── Cooldown check ────────────────────────────────────────────────────
    today_str = get_ist_now().date().strftime("%Y-%m-%d")
    last_quiz = user_data.get("last_quiz_date")

    if last_quiz == today_str:
        return False, (
            "⏳ <b>Cooldown Active!</b>\n\n"
            "You've already completed today's Quiz Trivia.\n"
            "Come back tomorrow for a new set of questions! 🧠\n\n"
            "<i>Resets daily at midnight IST.</i>"
        )

    return True, "✅ Eligible"


def check_answer(question: dict, selected_index: int) -> bool:
    """Verify if the selected answer index is correct.

    Args:
        question: The question dict from the question bank.
        selected_index: 0-indexed option selected by user.

    Returns:
        True if the answer is correct, False otherwise.
    """
    return selected_index == question["answer"]


def render_question(question: dict, question_number: int) -> str:
    """Render a quiz question as formatted text.

    Args:
        question: The question dict.
        question_number: 1-indexed question number (1, 2, or 3).

    Returns:
        Formatted HTML text for the question.
    """
    return (
        f"🧠 <b>QUIZ TRIVIA — Question {question_number}/{QUIZ_NUM_QUESTIONS}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"❓ <b>{question['q']}</b>\n\n"
        "<i>Select the correct answer below:</i>"
    )


def render_quiz_complete() -> str:
    """Render the quiz completion message (before claim)."""
    return (
        "🎉 <b>QUIZ COMPLETE!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "✅ You answered all 3 questions correctly!\n\n"
        f"🪙 Reward: <b>{QUIZ_REWARD_AMOUNT} Sparks</b>\n\n"
        "🔒 <b>Verify You're Human</b>\n"
        "Click the button below to verify and claim your Sparks.\n"
        "━━━━━━━━━━━━━━━━━━━━━━━"
    )
