"""
games_dummy.py
~~~~~~~~~~~~~~
Dummy file for testing FREE-TO-PLAY (F2P) Games.
Includes: Daily Tickets, Daily Spin, Idle Tycoon, and Leaderboard Quiz.
"""

import asyncio
import random
import time
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

router = Router(name="games_dummy")

# Dummy Database for F2P testing
F2P_DB = {}


def get_user_data(user_id: int):
    if user_id not in F2P_DB:
        F2P_DB[user_id] = {
            "tickets": 3,
            "sparks": 0,
            "last_spin": 0.0,
            "quiz_score": 0,
            "tycoon_lvl": 1,
            "tycoon_last_collect": time.time(),
        }
    return F2P_DB[user_id]


# ==========================================
# 🎮 MAIN F2P MENU
# ==========================================
@router.message(Command("games"))
async def cmd_games_menu(message: Message):
    await show_main_menu(message, message.from_user.id)


async def show_main_menu(message: Message, user_id: int, is_edit: bool = False):
    data = get_user_data(user_id)

    text = (
        "🎮 <b>FREE-TO-PLAY ARCADE (DUMMY)</b>\n\n"
        f"🎒 <b>Your Inventory:</b>\n"
        f"🪙 Sparks: <b>{data['sparks']}</b>\n"
        f"🎟️ Free Tickets: <b>{data['tickets']}</b>\n"
        f"🏆 Quiz Score: <b>{data['quiz_score']}</b>\n\n"
        "<i>Yahan aapka koi paisa/Sparks nahi katega. Sab free hai!</i>"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎟️ Ticket Arcade (Slots)", callback_data="dummy_f2p_slots"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎡 Daily Free Spin", callback_data="dummy_f2p_spin"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🌾 Free Idle Tycoon", callback_data="dummy_f2p_tycoon"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🧠 Leaderboard Trivia", callback_data="dummy_f2p_quiz"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Get +3 Free Tickets (Test)",
                    callback_data="dummy_add_tickets",
                )
            ],
        ]
    )

    if is_edit:
        await message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(F.data == "dummy_f2p_menu")
async def cb_back_menu(query: CallbackQuery):
    await show_main_menu(query.message, query.from_user.id, is_edit=True)
    await query.answer()


@router.callback_query(F.data == "dummy_add_tickets")
async def cb_add_tickets(query: CallbackQuery):
    data = get_user_data(query.from_user.id)
    data["tickets"] += 3
    await query.answer("Added +3 Tickets for testing!", show_alert=True)
    await show_main_menu(query.message, query.from_user.id, is_edit=True)


# ==========================================
# 1. 🎟️ TICKET ARCADE (SLOTS)
# ==========================================
@router.callback_query(F.data == "dummy_f2p_slots")
async def cb_f2p_slots(query: CallbackQuery):
    data = get_user_data(query.from_user.id)

    if data["tickets"] < 1:
        return await query.answer(
            "❌ You don't have any Free Tickets!", show_alert=True
        )

    data["tickets"] -= 1  # Deduct ONLY ticket, not sparks!

    msg = await query.message.edit_text(
        "🎰 <b>Ticket Slots...</b>\n\n[ 🔄 | 🔄 | 🔄 ]", parse_mode="HTML"
    )
    symbols = ["🍒", "💎", "🔔", "🍉"]

    for _ in range(2):
        await asyncio.sleep(0.4)
        s1, s2, s3 = (
            random.choice(symbols),
            random.choice(symbols),
            random.choice(symbols),
        )
        await msg.edit_text(
            f"🎰 <b>Ticket Slots...</b>\n\n[ {s1} | {s2} | {s3} ]", parse_mode="HTML"
        )

    await asyncio.sleep(0.4)

    # 30% chance to win for dummy testing
    if random.random() < 0.30:
        s1 = s2 = s3 = "💎"
        data["sparks"] += 100
        text = f"🎰 <b>RESULT</b>\n\n[ {s1} | {s2} | {s3} ]\n\n🎉 <b>YOU WON!</b> +100 Sparks!"
    else:
        s1, s2, s3 = (
            random.choice(symbols),
            random.choice(symbols),
            random.choice(symbols),
        )
        while s1 == s2 == s3:
            s3 = random.choice(symbols)
        text = f"🎰 <b>RESULT</b>\n\n[ {s1} | {s2} | {s3} ]\n\n😢 Ahh, better luck next time. (No Sparks lost!)"

    await msg.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔄 Use Another Ticket", callback_data="dummy_f2p_slots"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🔙 Back to Menu", callback_data="dummy_f2p_menu"
                    )
                ],
            ]
        ),
    )
    await query.answer()


# ==========================================
# 2. 🎡 DAILY FREE SPIN
# ==========================================
@router.callback_query(F.data == "dummy_f2p_spin")
async def cb_f2p_spin(query: CallbackQuery):
    data = get_user_data(query.from_user.id)

    # Normally 24 hours (86400 secs), using 10 seconds for testing
    if time.time() - data["last_spin"] < 10:
        remaining = 10 - int(time.time() - data["last_spin"])
        return await query.answer(
            f"⏳ Please wait {remaining} seconds for your next Daily Spin! (Normally 24 hours)",
            show_alert=True,
        )

    data["last_spin"] = time.time()

    msg = await query.message.edit_text(
        "🎡 <b>Spinning the Daily Wheel...</b> 🔄", parse_mode="HTML"
    )
    await asyncio.sleep(1.5)

    rewards = [
        ("10 Sparks", 10),
        ("50 Sparks", 50),
        ("100 Sparks", 100),
        ("Better Luck Tomorrow!", 0),
    ]
    prize_name, prize_val = random.choice(rewards)
    data["sparks"] += prize_val

    text = f"🎡 <b>DAILY SPIN RESULT</b>\n\n🎁 You got: <b>{prize_name}</b>"

    await msg.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔙 Back to Menu", callback_data="dummy_f2p_menu"
                    )
                ]
            ]
        ),
    )
    await query.answer()


# ==========================================
# 3. 🌾 IDLE TYCOON (PASSIVE)
# ==========================================
@router.callback_query(F.data == "dummy_f2p_tycoon")
async def cb_f2p_tycoon(query: CallbackQuery):
    data = get_user_data(query.from_user.id)

    minutes_passed = (time.time() - data["tycoon_last_collect"]) / 60
    uncollected = int(minutes_passed * (data["tycoon_lvl"] * 5))

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"📥 Collect {uncollected} Free Sparks",
                    callback_data="dummy_f2p_tycoon_col",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔙 Back to Menu", callback_data="dummy_f2p_menu"
                )
            ],
        ]
    )

    await query.message.edit_text(
        f"🌾 <b>FREE IDLE FARM</b>\n\n"
        f"Ye farm har minute free Sparks banata hai.\n"
        f"Earning Rate: {data['tycoon_lvl'] * 5} Sparks/min\n\n"
        f"💰 Uncollected: <b>{uncollected} Sparks</b>",
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    await query.answer()


@router.callback_query(F.data == "dummy_f2p_tycoon_col")
async def cb_f2p_tycoon_col(query: CallbackQuery):
    data = get_user_data(query.from_user.id)
    minutes_passed = (time.time() - data["tycoon_last_collect"]) / 60
    uncollected = int(minutes_passed * (data["tycoon_lvl"] * 5))

    if uncollected < 1:
        return await query.answer("Too soon! Wait a bit.", show_alert=True)

    data["sparks"] += uncollected
    data["tycoon_last_collect"] = time.time()
    await query.answer(f"✅ Collected {uncollected} Sparks!", show_alert=True)
    await cb_f2p_tycoon(query)


# ==========================================
# 4. 🧠 LEADERBOARD TRIVIA
# ==========================================
TRIVIA_QUESTIONS = [
    {
        "q": "What is the capital of India?",
        "options": ["Mumbai", "New Delhi", "Kolkata"],
        "ans": 1,
    },
    {
        "q": "Which planet is known as the Red Planet?",
        "options": ["Venus", "Mars", "Jupiter"],
        "ans": 1,
    },
    {
        "q": "How many seconds are in one hour?",
        "options": ["3600", "60", "2400"],
        "ans": 0,
    },
]


@router.callback_query(F.data == "dummy_f2p_quiz")
async def cb_f2p_quiz(query: CallbackQuery):
    q_data = random.choice(TRIVIA_QUESTIONS)

    # Store the correct answer index in the callback data for dummy testing
    buttons = []
    for idx, opt in enumerate(q_data["options"]):
        is_correct = "1" if idx == q_data["ans"] else "0"
        buttons.append(
            [
                InlineKeyboardButton(
                    text=opt, callback_data=f"dummy_quizans_{is_correct}"
                )
            ]
        )

    buttons.append(
        [InlineKeyboardButton(text="🔙 Back", callback_data="dummy_f2p_menu")]
    )

    await query.message.edit_text(
        f"🧠 <b>TRIVIA CHALLENGE</b>\n\n"
        f"<i>Question:</i> <b>{q_data['q']}</b>\n\n"
        f"Sahi jawab dekar apna Leaderboard Score badhayein! Har week top players ko prize milega.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await query.answer()


@router.callback_query(F.data.startswith("dummy_quizans_"))
async def cb_quiz_ans(query: CallbackQuery):
    data = get_user_data(query.from_user.id)
    is_correct = query.data.split("_")[-1] == "1"

    if is_correct:
        data["quiz_score"] += 10
        text = f"✅ <b>CORRECT!</b>\n\nYou got +10 Score. Your total score is now <b>{data['quiz_score']}</b>!"
    else:
        text = f"❌ <b>WRONG!</b>\n\nYour score is still <b>{data['quiz_score']}</b>."

    await query.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🧠 Next Question", callback_data="dummy_f2p_quiz"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🔙 Back to Menu", callback_data="dummy_f2p_menu"
                    )
                ],
            ]
        ),
    )
    await query.answer()
