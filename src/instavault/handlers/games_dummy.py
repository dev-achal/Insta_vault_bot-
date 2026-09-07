"""
games_dummy.py
~~~~~~~~~~~~~~
Dummy file for testing Telegram Native Animated Emojis (Excluding Dice/Slots).
Shows 5 different game logic variations using Dart, Basketball, Football, and Bowling.
"""

import asyncio
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

router = Router(name="games_dummy")

# Temporary memory for streak games
STREAK_SESSIONS = {}
PENALTY_SESSIONS = {}


# ==========================================
# 🏆 SPORTS ARCADE MENU
# ==========================================
@router.message(Command("sports"))
async def cmd_sports_menu(message: Message):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎯 Bullseye Challenge (High Risk)",
                    callback_data="anim_dart_bullseye",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎯 Dart Duel (Vs Bot)", callback_data="anim_dart_duel"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏀 Hoop Streak (Multiplier)", callback_data="anim_hoop_start"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⚽ Penalty Shootout (Best of 3)",
                    callback_data="anim_penalty_start",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎳 Bowling Multiplier", callback_data="anim_bowling"
                )
            ],
        ]
    )
    await message.answer(
        "🏆 <b>ANIMATED SPORTS ARCADE</b>\n\n"
        "Yahan Dice(🎲) aur Slots(🎰) ko chhod kar baaki 4 emojis ka use karke "
        "alag-alag 5 types ke games banaye gaye hain:\n\n"
        "Khel kar dekhiye:",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


@router.callback_query(F.data == "anim_back_menu")
async def cb_back_menu(query: CallbackQuery):
    await query.message.delete()
    await cmd_sports_menu(query.message)
    await query.answer()


# ==========================================
# 1. 🎯 BULLSEYE CHALLENGE (All or Nothing)
# ==========================================
@router.callback_query(F.data == "anim_dart_bullseye")
async def cb_dart_bullseye(query: CallbackQuery):
    await query.message.edit_text(
        "🎯 Throwing dart... If it hits the exact center, you win 10x!"
    )

    # Send native dart emoji
    msg = await query.message.answer_dice(emoji="🎯")
    await asyncio.sleep(2.5)  # Wait for animation

    val = msg.dice.value
    if val == 6:
        text = f"🎯 <b>BULLSEYE! (Value: {val})</b>\n\n🎉 BOOM! You hit the exact center! You win 10x multiplier!"
    else:
        text = f"🎯 <b>Missed Center (Value: {val})</b>\n\n😢 You missed the bullseye. You win nothing."

    await query.message.answer(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔄 Try Again", callback_data="anim_dart_bullseye"
                    )
                ],
                [InlineKeyboardButton(text="🔙 Menu", callback_data="anim_back_menu")],
            ]
        ),
    )
    await query.answer()


# ==========================================
# 2. 🎯 DART DUEL (PvE)
# ==========================================
@router.callback_query(F.data == "anim_dart_duel")
async def cb_dart_duel(query: CallbackQuery):
    await query.message.edit_text(
        "🎯 <b>DART DUEL!</b>\n\nYour turn first...", parse_mode="HTML"
    )

    # User's throw
    user_msg = await query.message.answer_dice(emoji="🎯")
    await asyncio.sleep(2.5)
    user_val = user_msg.dice.value

    await query.message.answer(
        f"👤 Your Score: <b>{user_val}</b>\n\nNow it's my (Bot's) turn...",
        parse_mode="HTML",
    )
    await asyncio.sleep(1.0)

    # Bot's throw
    bot_msg = await query.message.answer_dice(emoji="🎯")
    await asyncio.sleep(2.5)
    bot_val = bot_msg.dice.value

    if user_val > bot_val:
        result = "🎉 <b>YOU WIN!</b>"
    elif user_val < bot_val:
        result = "🤖 <b>BOT WINS!</b> You lose."
    else:
        result = "🤝 <b>IT'S A TIE!</b>"

    text = f"👤 You: {user_val} | 🤖 Bot: {bot_val}\n\n{result}"
    await query.message.answer(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔄 Rematch", callback_data="anim_dart_duel"
                    )
                ],
                [InlineKeyboardButton(text="🔙 Menu", callback_data="anim_back_menu")],
            ]
        ),
    )
    await query.answer()


# ==========================================
# 3. 🏀 HOOP STREAK (Crash Style Multiplier)
# ==========================================
@router.callback_query(F.data == "anim_hoop_start")
async def cb_hoop_start(query: CallbackQuery):
    STREAK_SESSIONS[query.from_user.id] = {"streak": 0, "multiplier": 1.0}
    await _render_hoop_menu(query)
    await query.answer()


async def _render_hoop_menu(query: CallbackQuery):
    session = STREAK_SESSIONS[query.from_user.id]
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🏀 Shoot Hoop (Risk)", callback_data="anim_hoop_shoot"
                )
            ],
            (
                [
                    InlineKeyboardButton(
                        text=f"💰 Cashout ({session['multiplier']}x)",
                        callback_data="anim_hoop_cashout",
                    )
                ]
                if session["streak"] > 0
                else []
            ),
            [InlineKeyboardButton(text="🔙 Menu", callback_data="anim_back_menu")],
        ]
    )
    text = f"🏀 <b>HOOP STREAK</b>\n\nStreak: <b>{session['streak']} Goals</b>\nCurrent Multiplier: <b>{session['multiplier']}x</b>\n\nShoot the ball! If you miss, you lose everything."

    if query.message.text and "HOOP STREAK" in query.message.text:
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    else:
        await query.message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "anim_hoop_shoot")
async def cb_hoop_shoot(query: CallbackQuery):
    session = STREAK_SESSIONS.get(query.from_user.id)
    if not session:
        return await query.answer("Session expired")

    await query.message.edit_text("🏀 <b>Shooting...</b>", parse_mode="HTML")
    msg = await query.message.answer_dice(emoji="🏀")
    await asyncio.sleep(2.5)  # Wait for basket animation

    val = msg.dice.value
    # Basketball values: 4 and 5 are GOALS. 1, 2, 3 are MISSES.
    if val >= 4:
        session["streak"] += 1
        session["multiplier"] = round(session["multiplier"] * 1.5, 1)  # 1.5x each goal
        await query.message.answer(
            f"✅ <b>GOAL!</b> (Value: {val})\nYour streak continues!", parse_mode="HTML"
        )
        await asyncio.sleep(1)
        await _render_hoop_menu(query)
    else:
        # Missed
        STREAK_SESSIONS.pop(query.from_user.id, None)
        await query.message.answer(
            f"❌ <b>MISSED!</b> (Value: {val})\n\nOh no! The ball bounced out. You lost your multiplier.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔄 Try Again", callback_data="anim_hoop_start"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🔙 Menu", callback_data="anim_back_menu"
                        )
                    ],
                ]
            ),
        )
    await query.answer()


@router.callback_query(F.data == "anim_hoop_cashout")
async def cb_hoop_cashout(query: CallbackQuery):
    session = STREAK_SESSIONS.pop(query.from_user.id, None)
    if not session:
        return await query.answer()

    await query.message.edit_text(
        f"💰 <b>CASHED OUT!</b>\n\nYou secured your <b>{session['multiplier']}x</b> multiplier safely!",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔄 Play Again", callback_data="anim_hoop_start"
                    )
                ],
                [InlineKeyboardButton(text="🔙 Menu", callback_data="anim_back_menu")],
            ]
        ),
    )
    await query.answer()


# ==========================================
# 4. ⚽ PENALTY SHOOTOUT (Best of 3)
# ==========================================
@router.callback_query(F.data == "anim_penalty_start")
async def cb_penalty_start(query: CallbackQuery):
    PENALTY_SESSIONS[query.from_user.id] = {"round": 1, "user_goals": 0, "bot_goals": 0}
    await _play_penalty_round(query, query.from_user.id)
    await query.answer()


async def _play_penalty_round(query: CallbackQuery, user_id: int):
    session = PENALTY_SESSIONS[user_id]
    if session["round"] > 3:
        # END GAME
        ug, bg = session["user_goals"], session["bot_goals"]
        if ug > bg:
            res = "🎉 <b>YOU WON THE MATCH!</b>"
        elif ug < bg:
            res = "🤖 <b>BOT WINS!</b>"
        else:
            res = "🤝 <b>DRAW!</b>"

        await query.message.answer(
            f"🏁 <b>FINAL SCORE</b>\nYou: {ug} | Bot: {bg}\n\n{res}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔄 Play Again", callback_data="anim_penalty_start"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🔙 Menu", callback_data="anim_back_menu"
                        )
                    ],
                ]
            ),
        )
        return

    await query.message.answer(
        f"⚽ <b>ROUND {session['round']} / 3</b>\n\n👤 <b>Your Kick:</b>",
        parse_mode="HTML",
    )
    u_msg = await query.message.answer_dice(emoji="⚽")
    await asyncio.sleep(2.5)

    if u_msg.dice.value >= 4:
        session["user_goals"] += 1
        await query.message.answer("✅ <b>GOAL for You!</b>", parse_mode="HTML")
    else:
        await query.message.answer("❌ <b>MISSED!</b>", parse_mode="HTML")

    await asyncio.sleep(1)
    await query.message.answer("🤖 <b>Bot's Kick:</b>", parse_mode="HTML")
    b_msg = await query.message.answer_dice(emoji="⚽")
    await asyncio.sleep(2.5)

    if b_msg.dice.value >= 4:
        session["bot_goals"] += 1
        await query.message.answer("✅ <b>GOAL for Bot!</b>", parse_mode="HTML")
    else:
        await query.message.answer("❌ <b>Bot MISSED!</b>", parse_mode="HTML")

    session["round"] += 1
    await asyncio.sleep(1)

    # Auto continue to next round
    await _play_penalty_round(query, user_id)


# ==========================================
# 5. 🎳 BOWLING MULTIPLIER (Dynamic Payout)
# ==========================================
@router.callback_query(F.data == "anim_bowling")
async def cb_bowling(query: CallbackQuery):
    await query.message.edit_text(
        "🎳 <b>Rolling the ball...</b>\n\nPayout is based on how many pins you knock down. Strike (6) pays massive!",
        parse_mode="HTML",
    )

    msg = await query.message.answer_dice(emoji="🎳")
    await asyncio.sleep(3.0)  # Bowling takes a bit longer

    val = msg.dice.value
    # Value 1 = gutter. Value 6 = Strike.
    if val == 6:
        text = f"🎳 <b>STRIKE! (Value: 6)</b>\n\n🎉 Incredible! You knocked them all down! Payout: <b>5.0x</b>"
    elif val == 1:
        text = (
            f"🎳 <b>GUTTERBALL (Value: 1)</b>\n\n😢 Ouch. 0 pins. Payout: <b>0.0x</b>"
        )
    else:
        # Values 2,3,4,5 give fractional payouts
        multiplier = round((val - 1) * 0.4, 1)
        text = f"🎳 <b>PINS DOWN (Value: {val})</b>\n\nNot bad! Payout: <b>{multiplier}x</b>"

    await query.message.answer(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔄 Roll Again", callback_data="anim_bowling"
                    )
                ],
                [InlineKeyboardButton(text="🔙 Menu", callback_data="anim_back_menu")],
            ]
        ),
    )
    await query.answer()
