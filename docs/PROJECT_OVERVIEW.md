# 📘 InstaVault Bot — Complete Project Overview

> **Last Updated:** 2026-06-13  
> **Purpose:** This document is the single source of truth for onboarding any new developer, AI agent, or contributor. Read this FIRST before touching any code.

---

## Table of Contents

1. [What Is InstaVault Bot?](#1-what-is-instavault-bot)
2. [Tech Stack & Dependencies](#2-tech-stack--dependencies)
3. [Project Directory Structure](#3-project-directory-structure)
4. [Environment Variables & Configuration](#4-environment-variables--configuration)
5. [Application Architecture & Boot Sequence](#5-application-architecture--boot-sequence)
6. [User Lifecycle & Data Flows](#6-user-lifecycle--data-flows)
7. [Firestore Database Schema](#7-firestore-database-schema)
8. [File-by-File Deep Breakdown](#8-file-by-file-deep-breakdown)
9. [Callback Routing Map (Complete)](#9-callback-routing-map-complete)
10. [Economy & Gamification System](#10-economy--gamification-system)
11. [FSM (Finite State Machine) States](#11-fsm-finite-state-machine-states)
12. [Deployment & Operations](#12-deployment--operations)
13. [Phase Roadmap & Current Status](#13-phase-roadmap--current-status)
14. [Known Patterns & Anti-Patterns](#14-known-patterns--anti-patterns)
15. [Quick Reference: Keyboard Functions](#15-quick-reference-keyboard-functions)
16. [Security Notes](#16-security-notes)

---

## 1. What Is InstaVault Bot?

InstaVault Bot is a **Telegram bot** that provides **free Instagram views** to creators through a virtual currency system called **Sparks (⚡)**. Users earn Sparks by completing daily missions, maintaining login streaks, opening mystery boxes, and referring friends. They spend Sparks to order real Instagram views.

**Core Value Proposition:**
- Users earn Sparks → Spend Sparks to get real Instagram views
- Rate: **500 Sparks = 1,000 Real Views**
- Revenue Model: Gaming app monetization → profits redirected as free views to users

**Target Audience:** Indian Instagram creators (bot language is Hinglish — Hindi + English)

---

## 2. Tech Stack & Dependencies

| Component | Technology | Version |
|-----------|-----------|---------|
| **Bot Framework** | [aiogram](https://docs.aiogram.dev/) (async Telegram Bot API) | 3.13.1 |
| **HTTP Server** | [aiohttp](https://docs.aiohttp.org/) | 3.10.10 |
| **Database** | [Firebase Firestore](https://firebase.google.com/docs/firestore) (async client) | firebase-admin 6.5.0 |
| **Environment** | python-dotenv | 1.0.1 |
| **Timezone** | pytz (Asia/Kolkata) | 2024.1 |
| **Language** | Python 3.10+ (uses `X | Y` union syntax) | |

### Key Framework Concepts (aiogram 3.x)
- **Router:** Each handler module has its own `Router()`. Routers are registered with the `Dispatcher` in `main.py`.
- **FSM (Finite State Machine):** Used for multi-step user interactions (onboarding, IG handle linking).
- **Callback Queries:** Inline keyboard button presses routed via `F.data` filters.
- **ParseMode.HTML:** All messages use HTML formatting, NOT Markdown.

---

## 3. Project Directory Structure

```
Insta_vault_bot-/
├── main.py                      # 🚀 Entry point — bot startup, webhook/polling mode
├── config.py                    # ⚙️ All configuration constants & economy values
├── requirements.txt             # 📦 Python dependencies
├── .env                         # 🔐 Environment variables (secrets)
├── .gitignore                   # Git exclusions
├── firebase_credentials.json    # 🔑 Firebase service account key (SECRET!)
├── manage_bot.sh                # 🛠️ Shell script for start/stop/restart/status/logs
├── bot.log                      # 📋 Runtime log file (auto-generated)
│
├── handlers/                    # 📨 All Telegram message & callback handlers
│   ├── __init__.py              # Empty (package marker)
│   ├── start.py                 # /start command, 3-beat onboarding flow, referral processing
│   ├── main_menu.py             # Dashboard, Profile, Rewards, Orders (nav), Mission, Leaderboard, Mystery Box, Streak Shield, IG linking
│   ├── orders.py                # /order command, package selection, order confirmation
│   └── referrals.py             # /refer command, referral stats display
│
├── keyboards/                   # ⌨️ All keyboard builders (inline & reply)
│   ├── __init__.py              # Empty (package marker)
│   ├── inline.py                # All InlineKeyboardMarkup builders (buttons inside messages)
│   └── reply.py                 # ReplyKeyboardMarkup builders (persistent bottom keyboard)
│
├── database/                    # 🗄️ Firestore initialization & all CRUD operations
│   ├── __init__.py              # Empty (package marker)
│   ├── firebase_init.py         # Firebase Admin SDK initialization, singleton client
│   └── db_manager.py            # ALL database operations (users, orders, transactions, waitlist)
│
└── utils/                       # 🔧 Shared utility functions
    ├── __init__.py              # Empty (package marker)
    └── helpers.py               # Timezone, ID generation, rank calculation, async executor
```

---

## 4. Environment Variables & Configuration

### `.env` File

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BOT_TOKEN` | ✅ Yes | — | Telegram bot token from @BotFather |
| `BOT_PORT` | No | `8099` | Port for aiohttp web server |
| `WEBHOOK_URL` | No | — | Full URL for production webhook (e.g. `https://your-app.onrender.com`). If set → webhook mode. If empty → polling mode. |
| `FIREBASE_CREDENTIALS_PATH` | No | `firebase_credentials.json` | Path to Firebase service account JSON |

### `config.py` Constants (Economy)

| Constant | Value | Description |
|----------|-------|-------------|
| `WELCOME_BONUS` | 500 | Sparks given on account creation |
| `DAILY_MISSION_REWARD` | 400 | Sparks per daily mission completion |
| `AD_WATCH_REWARD` | 150 | Sparks for watching an ad |
| `MYSTERY_BOX_MIN` | 25 | Minimum Sparks from mystery box |
| `MYSTERY_BOX_MAX` | 2000 | Maximum Sparks from mystery box |
| `SPARK_EXPIRY_DAYS` | 90 | Sparks expiration period |

### `config.py` Constants (Packages)

| Package | Sparks Cost | Views Delivered |
|---------|-------------|-----------------|
| Starter | 500 | 1,000 |
| Growth | 1,200 | 3,000 |
| Pro | 2,500 | 7,000 |
| Mega | 5,000 | 15,000 |

### `config.py` Constants (Referral)

| Constant | Value | Description |
|----------|-------|-------------|
| `REFERRAL_JOIN_BONUS` | 500 | Sparks given to referrer when friend joins |
| `REFERRAL_MISSION_BONUS` | 300 | Sparks for referrer on friend's mission |
| `REFEREE_BONUS` | 400 | Extra Sparks for the new user who joined via referral link |
| `PASSIVE_PERCENT` | 5 | % of friend's mission earnings passed to referrer |
| `PASSIVE_MONTHLY_CAP` | 500 | Monthly cap on passive referral earnings |

### `config.py` Constants (Other)

| Constant | Value | Description |
|----------|-------|-------------|
| `DAILY_LIMITS` | `{0:1, 3:2, 10:3, 25:4, 50:999}` | Daily order limits based on streak days |
| `VIP_SLOTS` | 1000 | Max VIP member slots |
| `DELIVERY_PROMISE_MINUTES` | 45 | Promised view delivery time |
| `COMPENSATION_TRIGGER_MINUTES` | 60 | Late delivery triggers compensation |
| `COMPENSATION_AMOUNT` | 200 | Sparks compensation for late delivery |
| `TIMEZONE` | `Asia/Kolkata` | All timestamps in IST |
| `BOT_USERNAME` | `""` (runtime) | Populated at startup via `bot.get_me()` |

> **Streak Milestones**, **Mystery Box tiers**, and the full **Earning/Spending economy** are documented once in [Section 10 — Economy & Gamification](#10-economy--gamification-system) to avoid duplication.

---

## 5. Application Architecture & Boot Sequence

### Mode Detection
The bot supports **two modes**, automatically selected at startup:

```
WEBHOOK_URL env var set?
  ├── YES → Webhook mode (Production — Render.com)
  │         aiohttp server receives POST at /webhook/<BOT_TOKEN>
  │         Binds 0.0.0.0:$PORT
  └── NO  → Polling mode (Development — Replit/local)
            Long polling + minimal health-check server on port
```

### Boot Sequence (both modes)

```
1. load_dotenv()              → Load .env variables
2. _build_bot_and_dispatcher()
   ├── Create Bot(token, HTML parse mode)
   ├── Create Dispatcher(MemoryStorage)
   └── Register routers (order matters!):
       ├── start.router       (most specific — /start, onboarding)
       ├── main_menu.router   (dashboard, profile, rewards, etc.)
       ├── orders.router      (order flow)
       └── referrals.router   (referral commands)
3. _verify_services(bot)
   ├── bot.get_me()           → Validate token, cache BOT_USERNAME
   └── Firestore ping         → db.collection("users").limit(1).get()
4. Start serving:
   ├── Polling: delete_webhook() + dp.start_polling()
   └── Webhook: set_webhook(url) + web.run_app()
```

### Health Check Endpoints
- `GET /` → `"bot is running"` (text/plain)
- `GET /healthz` → `{"status": "ok", "service": "InstaVault Bot", "mode": "webhook|polling"}` (JSON)

---

## 6. User Lifecycle & Data Flows

### New User Onboarding (3-Beat Psychological Flow)

```
User sends /start (with optional ?start=ref_VLTXXXXX deep link)
    │
    ▼
Beat 1: Greeting message
    │   "Arre {name} bhai, finally aa gaye!"
    │   Button: "Haan, mujhe Free Views chahiye! →"
    │   [ref_code embedded in callback_data — stateless]
    │
    ▼
Beat 2: Value proposition
    │   Shows Sparks system explanation
    │   Button: "🎁 Apna Welcome Bonus Claim Karo"
    │   Button: "📖 Yeh kya hota hai?" → Trust Screen → Back to Beat 2
    │
    ▼
Beat 3: Account creation (Firestore write happens HERE)
    │   ├── create_user() → Firestore document with all default fields
    │   ├── log_transaction() → welcome_bonus 500 Sparks
    │   ├── Referral processing (if referred):
    │   │   ├── get_user_by_referral_code() → find referrer
    │   │   ├── update_user() → store referrer UID
    │   │   ├── reward_referrer() → +500 Sparks, +1 referral_count
    │   │   ├── log_transaction() → referral_bonus for referrer
    │   │   ├── increment_spark_balance() → +400 referee_bonus for new user
    │   │   ├── log_transaction() → referee_bonus
    │   │   └── Send notification to referrer
    │   └── Clear FSM state
    │
    ▼
Post-Onboarding: Navigation buttons
    ├── "🚀 Aaj ka Mission Complete Karo" → nav_mission
    ├── "📊 Mera Dashboard" → nav_dashboard
    └── "🤝 Dost ko Refer Karo" → nav_refer
```

### Returning User Flow

```
User sends /start
    │
    ├── user_exists() → True
    ├── Clear FSM state
    ├── Send "Welcome back!" with ReplyKeyboardRemove
    └── show_dashboard() → Dashboard with lazy streak evaluation
```

### Order Flow

```
User taps "📦 Views Order Karo" (nav_order callback)
    │
    ├── IG handle check → If not set, redirect to Profile
    ├── Balance check → If < 500 Sparks, show empty state
    │
    ▼
Package Selection Screen
    ├── 🌱 Starter (500 Sparks → 1,000 views)
    ├── 🔥 Growth (1,200 Sparks → 3,000 views)  ⭐ BEST
    └── 💎 Pro (2,500 Sparks → 7,000 views)
        │
        ▼
    Confirmation Screen (cost breakdown)
        ├── ✅ Confirm → place_order_transactional()
        │   ├── Atomic: verify balance, deduct Sparks, create order doc, log tx
        │   └── Show success: "Views will be delivered within 45 minutes"
        └── ❌ Cancel → back to package selection
```

### Lazy Streak Engine

```
Dashboard load (show_dashboard called)
    │
    ├── get_user() → fetch user data
    ├── _run_lazy_streak():
    │   ├── Get today's IST date
    │   ├── Get last_login IST date
    │   ├── Calculate diff = today - last_login
    │   │
    │   ├── diff == 0 → Same day, no change
    │   ├── diff == 1 → Consecutive day, streak += 1
    │   ├── diff == 2 AND shields > 0 → Shield used, streak += 1
    │   └── diff > 2 (or diff == 2 with no shields) → streak = 1 (reset)
    │   │
    │   ├── Check milestone bonuses (Day 3/7/14/30)
    │   │   ├── increment_spark_balance() → atomic add
    │   │   ├── log_transaction() → streak_milestone_day_X
    │   │   └── query.answer(show_alert=True) → popup notification
    │   │
    │   └── update_user() → streak_days, last_login, streak_shields
    │
    └── Render dashboard with fresh values
```

---

## 7. Firestore Database Schema

### Collection: `users`
**Document ID:** Telegram user ID (string)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `first_name` | string | from Telegram | User's first name |
| `username` | string | `""` | Telegram @username |
| `vault_id` | string | `VLT-XXXXX` | Unique InstaVault ID |
| `join_date` | timestamp | now (IST) | Account creation date |
| `status` | string | `"active"` | Account status |
| `spark_balance` | int | 500 | Current Sparks balance |
| `lifetime_sparks` | int | 500 | Total Sparks ever earned |
| `rank_points` | int | 0 | Points for ranking |
| `rank_tier` | string | `"Rookie Vaulter"` | Current rank name |
| `streak_days` | int | 1 | Current login streak |
| `last_login` | timestamp | now (IST) | Last dashboard visit |
| `streak_shields` | int | 0 | Available streak shields (max 3) |
| `last_daily_reset` | timestamp | now (IST) | Last daily mission reset |
| `daily_level_count` | int | 0 | Missions completed today |
| `daily_limit` | int | 1 | Max missions today (based on streak) |
| `last_mystery_box_date` | string\|null | null | `"YYYY-MM-DD"` or null if never opened |
| `referral_code` | string | `ref_VLTXXXXX` | User's unique referral code |
| `referred_by` | string\|null | null | Referrer's user ID (or raw ref code pre-resolution) |
| `referral_count` | int | 0 | Number of successful referrals |
| `total_orders` | int | 0 | Total orders placed |
| `total_views_recv` | int | 0 | Total views received |
| `instagram_handle` | string\|null | null | Linked IG username (without @) |
| `first_order_date` | timestamp\|null | null | Date of first order |
| `power_score` | int | 0 | Gamification score |
| `jackpot_tickets` | int | 0 | Jackpot entry tickets |
| `notif_preference` | string | `"all"` | Notification settings |
| `is_vip_member` | bool | false | VIP status |
| `community_invited` | bool | false | Community invite status |
| `waitlist_pos` | int\|null | null | Waitlist position |
| `source_tag` | string | `"direct"` | How user found the bot |
| `onboarding_time` | string | `"unknown"` | Time slot of signup (morning/afternoon/evening/night) |
| `action_speed_ms` | int | 0 | Time from /start to Beat 3 in ms |

### Collection: `orders`
**Document ID:** Auto-generated

| Field | Type | Description |
|-------|------|-------------|
| `user_id` | string | Telegram user ID |
| `package_type` | string | `starter`, `growth`, `pro`, `mega` |
| `sparks_spent` | int | Sparks deducted |
| `views_ordered` | int | Views ordered |
| `instagram_url` | string | IG handle for delivery |
| `status` | string | `pending`, `delivered`, `cancelled` |
| `created_at` | timestamp | Order time (IST) |
| `delivered_at` | timestamp\|null | Delivery completion time |
| `compensation_given` | bool | Whether late-delivery compensation was given |

### Collection: `transactions`
**Document ID:** Auto-generated

| Field | Type | Description |
|-------|------|-------------|
| `user_id` | string | Telegram user ID |
| `type` | string | `earn`, `spend`, `bonus`, `referral`, `compensation` |
| `amount` | int | Sparks amount |
| `source` | string | Event source (e.g. `welcome_bonus`, `order_starter`, `mystery_box_open`) |
| `created_at` | timestamp | Transaction time (IST) |

### Collection: `waitlist`
**Document ID:** Telegram user ID (string)

| Field | Type | Description |
|-------|------|-------------|
| `first_name` | string | User's first name |
| `username` | string | Telegram @username |
| `position` | int | Waitlist position |
| `joined_at` | timestamp | Waitlist join time |
| `invite_count` | int | Friends invited while on waitlist |
| `activated` | bool | Whether user has been activated |

---

## 8. File-by-File Deep Breakdown

### `main.py` (220 lines)
**Role:** Application entry point and server setup.

| Function | Purpose |
|----------|---------|
| `_verify_services(bot)` | Startup self-check: validate bot token + Firestore connectivity. Exits with code 1 on failure. |
| `_build_bot_and_dispatcher()` | Factory: creates Bot + Dispatcher, registers all 4 routers in priority order. |
| `_run_polling()` | Development mode: health-check server + long polling. Clears stale webhooks. |
| `_on_startup_webhook(bot)` | Production webhook registration callback. |
| `_on_shutdown_webhook(bot)` | Production webhook cleanup callback. |
| `_create_webhook_app()` | Creates aiohttp app with webhook handler + health routes. |
| `index_handler(request)` | `GET /` → "bot is running" |
| `health_check(request)` | `GET /healthz` → JSON status |

**Router Registration Order:** `start` → `main_menu` → `orders` → `referrals` (most-specific first)

---

### `config.py` (58 lines)
**Role:** Centralized configuration. All constants are module-level variables.

**Important:** `BOT_USERNAME` is `""` at import time and gets populated at runtime by `_verify_services()` via `bot.get_me()`. Any code that needs the bot's username must read `config.BOT_USERNAME` at call time, not at import time.

**Mode Detection Logic:**
- `config.WEBHOOK_URL` is set from env, falling back to `REPLIT_DEV_DOMAIN` auto-detection.
- `WEBHOOK_PATH` = `/webhook/<BOT_TOKEN>`
- ⚠️ **Critical distinction:** `main.py` determines the actual run mode via `USE_WEBHOOK = bool(os.getenv("WEBHOOK_URL"))` — this reads the env var **directly**, NOT `config.WEBHOOK_URL`. So even if `REPLIT_DEV_DOMAIN` is set (making `config.WEBHOOK_URL` non-None), the bot will still use **polling mode** unless the explicit `WEBHOOK_URL` env var is set.

---

### `handlers/start.py` (393 lines)
**Role:** New user onboarding (3-beat flow) + returning user redirect + post-onboarding navigation.

| Handler | Trigger | Purpose |
|---------|---------|---------|
| `cmd_start` | `/start` command | Entry: returning user → dashboard, new user → Beat 1 |
| `cb_beat_2` | `ob_beat_2:*` callback | Beat 2: value proposition (edits message) |
| `cb_how_it_works` | `ob_how_it_works:*` callback | Trust screen (edits message) |
| `cb_beat_3` | `ob_beat_3:*` callback | Beat 3: account creation + referral rewards |
| `cb_nav_dashboard` | `nav_dashboard` callback | Post-onboarding → Dashboard |
| `cb_nav_mission` | `nav_mission` callback | Post-onboarding → Mission screen |
| `cb_nav_refer` | `nav_refer` callback | Post-onboarding → Referral screen |

**Key Design:**
- Referral code is carried **statelessly** via `callback_data` (format: `ob_beat_2:ref_VLTXXXXX`), NOT in FSM. This makes it crash-proof across bot restarts.
- FSM (`OnboardingState.in_progress`) stores identity/timing for segmentation only.
- Idempotent: `user_exists()` guard prevents double-creation on double-tap.

---

### `handlers/main_menu.py` (923 lines)
**Role:** The largest handler file — owns most of the bot's screens.

| Screen | Handler(s) | Nav Callback |
|--------|-----------|-------------|
| 🏠 Dashboard | `show_dashboard()`, `cmd_dashboard`, `cb_go_dashboard` | `go_dashboard` |
| 🚀 Mission | `cmd_mission` | (nav_mission owned by start.py) |
| 📦 Order | `cb_nav_order`, `_render_order_screen` | `nav_order` |
| 🎁 Rewards | `cmd_rewards`, `cb_nav_rewards`, `_render_rewards_screen` | `nav_rewards` |
| 📊 Profile | `cmd_profile`, `cb_nav_profile`, `_render_profile_screen` | `nav_profile` |
| 🎰 Mystery Box | `cb_mystery_box` | `action_mystery_box` |
| 🏆 Leaderboard | `cb_nav_leaderboard` | `nav_leaderboard` |
| 📦 Order History | `cb_nav_order_history`, `cb_order_history_page`, `_render_order_history` | `nav_order_history` |
| 🛡️ Streak Shield | `cb_buy_shield`, `cb_shields_full`, `cb_use_shield` | `action_buy_shield`, `action_shields_full`, `use_shield` |
| 📸 IG Linking | `cb_action_link_ig`, `handle_ig_input`, `cmd_cancel_link` | `action_link_ig` |
| ❓ Help | `cmd_help` | — |
| 🚧 Coming Soon | `cb_coming_soon` | Various placeholder callbacks |

**Critical Functions:**
- `_run_lazy_streak()` — Evaluates streak on every dashboard load. Handles milestone bonuses and streak shield auto-consumption.
- `_clean_ig_handle()` — Strips URL/@ noise from Instagram handle input.
- `show_dashboard()` — Renders dashboard with streak. The `query` parameter is answered exactly once (either via milestone popup or silent answer).

**Coming Soon Callbacks:** See [Section 9 — Callback Routing Map](#9-callback-routing-map-complete) for the complete list of 9 placeholder callbacks routed to `cb_coming_soon`.

---

### `handlers/orders.py` (216 lines)
**Role:** Order command and package selection/confirmation flow.

| Handler | Trigger | Purpose |
|---------|---------|---------|
| `cmd_order` | `/order` command or "📦 Order Views" text | Show package selection (with IG guard) |
| `cb_select_package` | `order_pkg_starter`, `order_pkg_growth`, `order_pkg_pro` | Show confirmation screen |
| `cb_confirm_order` | `order_confirm:<package_type>` | Atomic order placement |
| `cb_cancel_order` | `order_cancel` | Cancel order |

**Key Design:**
- Uses `place_order_transactional()` for atomic Firestore transaction (prevents double-spending).
- IG handle guard: won't let user order without linking Instagram first.

---

### `handlers/referrals.py` (54 lines)
**Role:** `/refer` command — displays referral stats and shareable link.

**Note:** The actual referral reward logic is in `start.py` (Beat 3), not here. This file only displays info.

---

### `keyboards/inline.py` (396 lines)
**Role:** All `InlineKeyboardMarkup` builder functions.

See [Quick Reference: Keyboard Functions](#15-quick-reference-keyboard-functions) for the complete list.

---

### `keyboards/reply.py` (53 lines)
**Role:** Reply keyboard builders (persistent bottom keyboards).

| Function | Purpose |
|----------|---------|
| `main_menu_keyboard()` | Main bottom navigation (Dashboard, Mission, Order, Rewards, Profile, Refer, Help) |
| `cancel_keyboard()` | Single "❌ Cancel" button for multi-step flows |
| `share_contact_keyboard()` | "📱 Share Contact" + "⏭ Skip" (onboarding use) |

**Note:** The current codebase uses `ReplyKeyboardRemove` in onboarding and relies primarily on inline keyboards for navigation. Reply keyboards are mostly unused in the current flow.

---

### `database/firebase_init.py` (58 lines)
**Role:** Firebase Admin SDK initialization (singleton pattern).

| Function | Purpose |
|----------|---------|
| `init_firebase()` | Initialize Firebase SDK, return async Firestore client. Safe to call multiple times (idempotent). |
| `get_db()` | Return the already-initialized client. Raises `RuntimeError` if not initialized. |

**Credential Resolution:**
1. Check `FIREBASE_CREDENTIALS_PATH` env var
2. Fall back to `firebase_credentials.json` in project root
3. Handle both absolute and relative paths

---

### `database/db_manager.py` (659 lines)
**Role:** ALL Firestore CRUD operations. The data access layer.

**Collections Used:** `users`, `orders`, `transactions`, `waitlist`

**Custom Exceptions:**
| Exception | Raised When |
|-----------|-------------|
| `InsufficientSparksError` | User doesn't have enough Sparks |
| `UserNotFoundError` | User document not found in Firestore |
| `CooldownActiveError` | Mystery box already opened today |
| `MaxShieldsReachedError` | User already has max (3) streak shields |

**User Operations:**
| Function | Description |
|----------|-------------|
| `user_exists(user_id)` | Check if user doc exists |
| `get_user(user_id)` | Fetch user dict or None |
| `create_user(...)` | Create user with all default fields |
| `update_user(user_id, fields)` | Partial field update |
| `increment_spark_balance(user_id, amount)` | Atomic increment using Firestore `Increment` sentinel |
| `deduct_spark_balance(user_id, amount)` | Atomic deduction |
| `update_last_login(user_id)` | Stamp last_login with IST now |

**Referral Operations:**
| Function | Description |
|----------|-------------|
| `get_user_by_referral_code(code)` | Query user by referral_code field |
| `reward_referrer(referrer_id)` | Atomic: +500 Sparks, +1 referral_count |

**Leaderboard:**
| Function | Description |
|----------|-------------|
| `get_leaderboard(limit)` | Top users by spark_balance (descending) |

**Order Operations:**
| Function | Description |
|----------|-------------|
| `create_order(...)` | Create order doc (auto-ID) |
| `place_order_transactional(...)` | **Firestore Transaction:** verify balance → deduct → create order → log tx (atomic) |
| `get_order(order_id)` | Fetch single order |
| `get_user_orders(user_id, limit)` | User's orders, newest first (Python-sorted) |
| `update_order_status(order_id, ...)` | Update order status/delivery |

**Transactional Operations (Atomic):**
| Function | Description |
|----------|-------------|
| `open_mystery_box_transactional(...)` | Cooldown check → balance check → deduct cost → add winnings → log double-ledger |
| `buy_streak_shield_transactional(...)` | Shield limit check → balance check → deduct → increment shields → log tx |

**Transaction Log:**
| Function | Description |
|----------|-------------|
| `log_transaction(user_id, tx_type, amount, source)` | Create transaction record |
| `get_user_transactions(user_id, limit)` | User's transactions (newest first, Firestore-sorted) |

**Waitlist:**
| Function | Description |
|----------|-------------|
| `add_to_waitlist(...)`, `get_waitlist_entry(...)`, `get_waitlist_count()`, `update_waitlist_entry(...)`, `activate_waitlist_user(...)` | Full waitlist CRUD |

---

### `utils/helpers.py` (112 lines)
**Role:** Shared utility functions used across the codebase.

| Function | Purpose |
|----------|---------|
| `get_ist_now()` | Current datetime in `Asia/Kolkata` timezone |
| `format_timestamp(dt, fmt)` | Format datetime as IST string. Returns `"N/A"` for None. |
| `generate_vault_id(numeric_part)` | Generate `VLT-XXXXX` format ID |
| `generate_referral_code(vault_id)` | Derive `ref_VLTXXXXX` from vault ID |
| `generate_short_code(length)` | Random alphanumeric code |
| `run_sync(func, *args)` | Run blocking function in thread executor |
| `get_rank_tier(rank_points)` | Calculate rank tier from points |
| `get_daily_limit(streak_days)` | Calculate daily order limit from streak |

**Rank Tiers:**
| Tier | Min Points |
|------|-----------|
| Rookie | 0 |
| Rising | 500 |
| Hustler | 2,000 |
| Elite | 6,000 |
| VaultKing | 15,000 |

---

### `manage_bot.sh` (98 lines)
**Role:** Shell script for bot process management.

| Command | Usage | Action |
|---------|-------|--------|
| `start` | `./manage_bot.sh start` | Start bot in background via nohup |
| `stop` | `./manage_bot.sh stop` | Stop bot (SIGTERM → SIGKILL fallback) |
| `restart` | `./manage_bot.sh restart` | Stop then start |
| `status` | `./manage_bot.sh status` | Show running status + recent logs |
| `logs` | `./manage_bot.sh logs` | Tail -f bot.log |

---

## 9. Callback Routing Map (Complete)

This is the most important reference for understanding button interactions.

### `start.py` Router

| Callback Data | Handler | Action |
|---------------|---------|--------|
| `ob_beat_2:<ref_code>` | `cb_beat_2` | Edit → Beat 2 value proposition |
| `ob_how_it_works:<ref_code>` | `cb_how_it_works` | Edit → Trust screen |
| `ob_beat_3:<ref_code>` | `cb_beat_3` | Account creation + dashboard |
| `nav_dashboard` | `cb_nav_dashboard` | → `show_dashboard()` |
| `nav_mission` | `cb_nav_mission` | Edit → Mission screen |
| `nav_refer` | `cb_nav_refer` | Edit → Referral screen |

### `main_menu.py` Router

| Callback Data | Handler | Action |
|---------------|---------|--------|
| `go_dashboard` | `cb_go_dashboard` | Edit → Dashboard (with streak) |
| `nav_order` | `cb_nav_order` | Edit → Order screen (IG guard) |
| `nav_rewards` | `cb_nav_rewards` | Edit → Rewards Center |
| `nav_profile` | `cb_nav_profile` | Edit → Profile screen |
| `nav_leaderboard` | `cb_nav_leaderboard` | Edit → Leaderboard |
| `nav_order_history` | `cb_nav_order_history` | Edit → Order History (page 0) |
| `order_history_page:<N>` | `cb_order_history_page` | Edit → Order History (page N) |
| `action_mystery_box` | `cb_mystery_box` | Mystery Box open + result |
| `action_buy_shield` | `cb_buy_shield` | Buy streak shield (200 Sparks) |
| `action_shields_full` | `cb_shields_full` | Alert: max shields reached |
| `use_shield` | `cb_use_shield` | Alert: shields are auto-used ⚠️ *Orphan handler — no keyboard button in `inline.py` generates this callback. Handler exists but is currently unreachable.* |
| `action_link_ig` | `cb_action_link_ig` | FSM → prompt for IG handle |
| `dummy_app_link` | `cb_coming_soon` | 🚧 Coming soon alert |
| `order_pkg_mega` | `cb_coming_soon` | 🚧 Coming soon alert |
| `contact_support` | `cb_coming_soon` | 🚧 Coming soon alert |
| `faq` | `cb_coming_soon` | 🚧 Coming soon alert |
| `mission_start` | `cb_coming_soon` | 🚧 Coming soon alert |
| `mystery_box_open` | `cb_coming_soon` | 🚧 Coming soon alert |
| `jackpot_tickets` | `cb_coming_soon` | 🚧 Coming soon alert |
| `notif_settings` | `cb_coming_soon` | 🚧 Coming soon alert |
| `tx_history` | `cb_coming_soon` | 🚧 Coming soon alert |

### `orders.py` Router

| Callback Data | Handler | Action |
|---------------|---------|--------|
| `order_pkg_starter` | `cb_select_package` | Confirm screen: Starter |
| `order_pkg_growth` | `cb_select_package` | Confirm screen: Growth |
| `order_pkg_pro` | `cb_select_package` | Confirm screen: Pro |
| `order_confirm:<pkg>` | `cb_confirm_order` | Atomic order placement |
| `order_cancel` | `cb_cancel_order` | Cancel order |

---

## 10. Economy & Gamification System

> Config constant names for these values are in [Section 4](#4-environment-variables--configuration). This section provides the **gameplay context** (frequency, earn vs. spend).

### Earning Sparks
| Source | Amount | Frequency |
|--------|--------|-----------|
| Welcome Bonus | 500 | One-time |
| Referee Bonus (joined via link) | 400 | One-time |
| Daily Mission | 400 | Daily |
| Mystery Box | 25–2,000 (weighted) | Daily (costs 100 Sparks) |
| Streak Milestone (Day 3) | 100 | One-time |
| Streak Milestone (Day 7) | 300 | One-time |
| Streak Milestone (Day 14) | 750 | One-time |
| Streak Milestone (Day 30) | 1,500 | One-time |
| Referral Bonus (for referrer) | 500 | Per referral |

### Spending Sparks
| Usage | Cost |
|-------|------|
| Starter views (1,000) | 500 |
| Growth views (3,000) | 1,200 |
| Pro views (7,000) | 2,500 |
| Mega views (15,000) | 5,000 |
| Mystery Box | 100 |
| Streak Shield | 200 |

### Mystery Box Probability Distribution

| Tier | Sparks Range | Weight (%) |
|------|-------------|-----------|
| Common | 25 – 75 | 50% |
| Uncommon | 100 – 300 | 30% |
| Rare | 350 – 750 | 15% |
| Legendary | 1,000 – 2,000 | 5% |

### Streak Shield Mechanics
- **Cost:** 200 Sparks each
- **Max:** 3 shields at a time
- **Auto-use:** If user misses exactly 1 day (diff == 2), system auto-consumes 1 shield and continues the streak
- **If diff > 2:** Streak resets to 1 regardless of shields

---

## 11. FSM (Finite State Machine) States

### `OnboardingState` (in `handlers/start.py`)

| State | When Active | Data Stored |
|-------|------------|-------------|
| `in_progress` | User is mid-onboarding (Beat 1 → Beat 3) | `start_ts`, `user_id`, `first_name`, `username` |

### `ProfileState` (in `handlers/main_menu.py`)

| State | When Active | Data Stored |
|-------|------------|-------------|
| `waiting_for_ig_handle` | User tapped "Link Instagram" and bot is waiting for text input | None (user_id from message) |

**Important:** FSM uses `MemoryStorage`, which means **all state is lost on bot restart**. The onboarding flow is designed to be crash-proof by carrying the referral code statelessly in callback_data.

---

## 12. Deployment & Operations

### Development (Polling Mode)
```bash
#                                                                                  Install dependencies
pip install -r requirements.txt

# Configure .env (set BOT_TOKEN, leave WEBHOOK_URL empty)

# Run
python3 main.py
```

### Production (Webhook Mode — Render.com)
```bash
# Set environment variables on Render:
# BOT_TOKEN=<your_token>
# WEBHOOK_URL=https://your-app.onrender.com
# FIREBASE_CREDENTIALS_PATH=firebase_credentials.json
# BOT_PORT=8099

# Start command:
python3 main.py
```

### Process Management (manage_bot.sh)
```bash
chmod +x manage_bot.sh
./manage_bot.sh start     # Start in background
./manage_bot.sh stop      # Stop gracefully
./manage_bot.sh restart   # Stop + start
./manage_bot.sh status    # Check if running + recent logs
./manage_bot.sh logs      # Tail -f bot.log
```

---

## 13. Phase Roadmap & Current Status

| Phase | Feature | Status |
|-------|---------|--------|
| Phase 1 | Basic bot structure, initial commands | ✅ Complete |
| Phase 2 | 3-Beat Onboarding, Referral System, Segmentation | ✅ Complete |
| Phase 3 | 5 Core Screens (Dashboard, Mission, Order, Rewards, Profile) | ✅ Complete |
| Phase 4 | Lazy Streak, Mystery Box, Leaderboard, Streak Shield | ✅ Complete |
| Phase 5 | Full delivery tracking, Mega package, Passive referrals, Dynamic bot username | 🔧 Partial (bot username done, rest pending) |
| Phase 6 | Instagram Handle Linking (FSM), Order History pagination | ✅ Complete |

### Features Still Marked "Coming Soon"
- App link for mission completion (`dummy_app_link`)
- Mega package ordering (`order_pkg_mega`)
- Contact Support (`contact_support`)
- FAQ screen (`faq`)
- Mission start flow (`mission_start`)
- Mystery box open animation (`mystery_box_open`)
- Jackpot tickets system (`jackpot_tickets`)
- Notification settings (`notif_settings`)
- Transaction history UI (`tx_history`)
- Passive referral earnings (5% of friend's missions)
- Full delivery tracking pipeline

---

## 14. Known Patterns & Anti-Patterns

### Patterns (Follow These)
1. **Stateless callback data:** Always carry important data (like referral codes) in callback_data, not FSM — makes flows crash-proof.
2. **Single query.answer():** Every callback handler must call `query.answer()` exactly ONCE. Multiple calls crash the bot.
3. **Edit vs. Answer:** Inline button navigations should `edit_text()` (edit "in-place). Commands should `answer()` (new message).
4. **Atomic transactions:** All balance-modifying operations that involve reads + writes must use Firestore transactions (`@async_transactional`) to prevent race conditions.
5. **Firestore Increment:** For simple additions/subtractions, use `Increment(n)` sentinel instead of read-modify-write.
6. **Idempotent handlers:** Guard against double-taps (e.g., `user_exists()` check before `create_user()`).
7. **ReplyKeyboardRemove:** Always clear stale reply keyboards in returning user path.

### Anti-Patterns (Avoid These)
1. ❌ Never use `ReplyKeyboardMarkup` in inline navigation flows.
2. ❌ Never call `query.answer()` more than once per callback handler.
3. ❌ Never do non-atomic read-then-write for Sparks balance changes.
4. ❌ Never import `BOT_USERNAME` at module level as a constant — it's populated at runtime.
5. ❌ Never add `/order` or `F.text == "📦 Order Views"` handlers outside `orders.py`.

---

## 15. Quick Reference: Keyboard Functions

### `keyboards/inline.py`

| Function | Used By | Returns |
|----------|---------|---------|
| `onboarding_beat1_keyboard(ref_code)` | `start.py` | Beat 1 CTA button |
| `onboarding_beat2_keyboard(ref_code)` | `start.py` | Beat 2: Claim Bonus + How it Works |
| `onboarding_beat3_keyboard()` | `start.py` | Post-onboarding: Mission, Dashboard, Refer |
| `onboarding_trust_keyboard(ref_code)` | `start.py` | Trust screen: Back to Beat 2 |
| `dashboard_keyboard()` | `main_menu.py` | Main dashboard: Mission, Order, Rewards, Profile, Refer, Leaderboard |
| `mission_keyboard()` | `start.py`, `main_menu.py` | Mission: App Link (coming soon) + Back |
| `order_keyboard_full()` | `orders.py`, `main_menu.py` | Package selection (3 packages + Back) |
| `order_keyboard_empty()` | `orders.py`, `main_menu.py` | Low balance: Mission + Rewards + Back |
| `rewards_keyboard(shields)` | `main_menu.py` | Mystery Box + Shield Buy/Full + Back |
| `profile_keyboard(ig_linked)` | `main_menu.py` | Link/Edit IG + Order History + Back |
| `mystery_box_result_keyboard()` | `main_menu.py` | Post-box: Back to Dashboard |
| `leaderboard_keyboard()` | `main_menu.py` | Back to Dashboard |
| `confirm_order_keyboard(package_type)` | `orders.py` | Confirm + Cancel |
| `referral_keyboard(referral_code)` | `start.py`, `referrals.py` | Share Link + Back |
| `order_history_keyboard(...)` | `main_menu.py` | Prev/Next pagination + Profile + Dashboard |
| `help_keyboard()` | `main_menu.py` | Contact Support + FAQ + Back |

---

## 16. Security Notes

> [!CAUTION]
> - `firebase_credentials.json` contains a private key. It is `.gitignore`d but exists on disk. Never commit it.
> - `.env` contains `BOT_TOKEN`. Also `.gitignore`d.
> - The `BOT_TOKEN` is exposed in plaintext in the webhook path (`/webhook/<token>`). This is standard Telegram practice but should be noted.
> - All `*.json` and `*.md` files are gitignored. This documentation file (`PROJECT_OVERVIEW.md`) will also be gitignored by default.

---

> **For agents:** This document should give you 100% context to start working on any part of the codebase without reading every file. If you need to modify a specific file, refer to the file breakdown section and callback routing map first.
