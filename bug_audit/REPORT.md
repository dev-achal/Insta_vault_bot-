# InstaVault Codebase Bug Audit Report

Running totals:
Critical / High / Medium / Low / Needs-confirmation = 13/21/22/14/9

---

## Phase 1 — Foundation & config

### [CRITICAL] Webhook Deletion on Shutdown Causes Rolling Deployment Outage
- File: `src/instavault/__main__.py`
- Line(s): 249-260
- Category: Race Condition / Availability
- What's wrong: In `_on_shutdown_webhook`, `await bot.delete_webhook(drop_pending_updates=False)` is executed unconditionally whenever the bot process shuts down.
- Why it matters: In cloud container deployments (Render, Kubernetes, Docker), rolling updates launch the new container before terminating the old one. When the old container receives `SIGTERM` and shuts down, its shutdown hook unregisters the Telegram webhook that the newly started container just registered, immediately severing all incoming updates and causing total bot downtime until manually reconfigured.
- Fix direction: Remove `bot.delete_webhook()` from `_on_shutdown_webhook`, retaining it only when explicitly switching to long polling mode.

### [CRITICAL] Swallowed Ban Cache Initialization Failure Bypasses All User Bans
- File: `src/instavault/__main__.py`
- Line(s): 100-105
- Category: Security / Error Handling
- What's wrong: In `_verify_services`, failure during `await init_ban_cache()` is caught and logged with `logger.error` without terminating startup (`sys.exit(1)`) or activating a database fallback mode.
- Why it matters: If Firestore suffers a transient network error or timeout during startup, `BANNED_USER_CACHE` remains an empty set (`set()`). Because `BanCheckMiddleware` checks only this in-memory cache without a fallback query, all previously banned fraudsters and bot abusers bypass ban protection and can freely access handlers, claim missions, and manipulate balances.
- Fix direction: Terminate startup via `sys.exit(1)` on ban cache failure, or configure `BanCheckMiddleware` to query Firestore directly if the cache failed initialization.

### [HIGH] Secret BOT_TOKEN Exposed in Webhook URL Path & Missing Secret Token Header Validation
- File: `src/instavault/core/config.py` & `src/instavault/__main__.py`
- Line(s): `src/instavault/core/config.py:61`, `src/instavault/__main__.py:243, 275-276`
- Category: Security
- What's wrong: `WEBHOOK_PATH` is defined as `f"/webhook/{BOT_TOKEN}"`, exposing the raw bot authentication token in the URL path, while `SimpleRequestHandler` and `bot.set_webhook` do not configure or validate Telegram's `secret_token` header.
- Why it matters: HTTP request paths are logged in plain text by reverse proxies, load balancers, CDN providers, and hosting platform log aggregators (e.g. Render access logs), leaking the bot's secret credentials. Furthermore, omitting `secret_token` allows anyone who discovers the webhook URL to post forged updates directly to the bot.
- Fix direction: Use a static unguessable path or UUID for `WEBHOOK_PATH`, and supply a dedicated `secret_token` to `bot.set_webhook` and `SimpleRequestHandler`.

### [HIGH] Inverted Webhook vs Polling Mode Detection Between Config and Main
- File: `src/instavault/core/config.py` & `src/instavault/__main__.py`
- Line(s): `src/instavault/core/config.py:56-59`, `src/instavault/__main__.py:6-13, 58, 312-318`
- Category: Logic / Startup
- What's wrong: `__main__.py` specifies in its architecture docstring that Replit development (`REPLIT_DEV_DOMAIN`) must use long polling, while production uses webhooks. However, `core/config.py` sets `WEBHOOK_URL` to `https://{_replit_domain}`, causing `USE_WEBHOOK = bool(WEBHOOK_URL)` to evaluate to `True` on Replit, while production deployments without an explicit `WEBHOOK_URL` env var unexpectedly fall back to polling mode.
- Why it matters: Replit dev environments fail to receive Telegram webhook POST updates without reverse proxy routing; conversely, production instances without `WEBHOOK_URL` run polling mode instead of properly binding to the webhook server port.
- Fix direction: Do not populate `WEBHOOK_URL` from `REPLIT_DEV_DOMAIN`, and explicitly validate webhook versus polling mode based on a dedicated environment flag.

### [HIGH] Ephemeral MemoryStorage Used for FSM Despite Mandatory Redis Dependency
- File: `src/instavault/__main__.py`
- Line(s): 26, 120
- Category: FSM / Concurrency
- What's wrong: `Dispatcher` is initialized with `storage=MemoryStorage()`, storing conversation states in the local Python process memory despite Redis already being configured as a mandatory service (`REDIS_URL`).
- Why it matters: Every bot restart, deployment, or worker restart immediately destroys all active user and admin FSM conversation states, corrupting in-progress order placements, Instagram account verification sessions, and admin user balance adjustments.
- Fix direction: Replace `MemoryStorage()` with `RedisStorage` using the existing Redis connection pool.

### [MEDIUM] Health Check Endpoint Returns HTTP 200 OK on Database Outage
- File: `src/instavault/__main__.py`
- Line(s): 291-305
- Category: Error Handling / Operations
- What's wrong: In `health_check()`, when the Firestore connectivity ping fails with an exception, the handler catches the error and returns `web.json_response({"status": "error", ...})` without an explicit HTTP error status code, defaulting to HTTP 200 OK.
- Why it matters: Container orchestrators, uptime probes, and load balancers rely on HTTP status codes (expecting 5xx on failure). Returning 200 OK masks complete database disconnects, preventing automated container restarts, alerts, or traffic failover.
- Fix direction: Pass `status=503` (or `500`) to `web.json_response` when `status == "error"`.

### [MEDIUM] BOT_USERNAME Missing from core/config.py and Dynamically Injected at Runtime
- File: `src/instavault/core/config.py` & `src/instavault/constants/rewards.py`
- Line(s): `src/instavault/core/config.py:1-73`, `src/instavault/constants/rewards.py:34`, `src/instavault/__main__.py:73`
- Category: Data Validation / Maintainability
- What's wrong: `BOT_USERNAME` is defined only in `constants/rewards.py:34` as an unreferenced empty string, and omitted entirely from `core/config.py`. Instead, `__main__.py` dynamically monkey-patches `_config.BOT_USERNAME = bot_info.username` inside `_verify_services()`.
- Why it matters: Any statement doing `from instavault.core.config import BOT_USERNAME` immediately fails with `ImportError`. If any handler or utility accesses `config.BOT_USERNAME` before `_verify_services()` runs (or in test environments), an `AttributeError` is thrown. Additionally, `referrals.py:39` and `start.py:351` use `config.BOT_USERNAME` without fallbacks, creating invalid deep links (`https://t.me/?start=...`) if empty.
- Fix direction: Declare `BOT_USERNAME: str = ""` in `core/config.py`, remove the orphaned declaration from `rewards.py`, and provide fallback strings in deep link builders.

### [MEDIUM] Incomplete Relative Path Handling for FIREBASE_CREDENTIALS_PATH
- File: `src/instavault/core/config.py`
- Line(s): 65-72
- Category: Config / Startup
- What's wrong: `FIREBASE_CREDENTIALS_PATH` is only converted to an absolute path pointing to the project root if its string value strictly equals `"firebase_credentials.json"`. If specified as any other relative path (e.g. `"./firebase_credentials.json"` or `"config/firebase.json"`), it is left unresolved.
- Why it matters: If the application or a test runner is executed from any working directory other than the project root, `firebase_init.py` will fail to locate the file and terminate with `FileNotFoundError`.
- Fix direction: Resolve any relative path against the project root directory using `os.path.abspath` or `pathlib.Path`.

### [MEDIUM] Missing SIGTERM Graceful Shutdown Handler in Polling Mode
- File: `src/instavault/__main__.py`
- Line(s): 219-226
- Category: Async Correctness / Resources
- What's wrong: `_run_polling()` wraps `dp.start_polling()` in a `try...finally` block. On Linux, `SIGTERM` signals sent by container runtimes or process managers terminate the process immediately without raising Python's `KeyboardInterrupt`.
- Why it matters: The `finally:` block (responsible for `runner.cleanup()`, `bot.session.close()`, and `close_redis()`) will not execute upon receiving `SIGTERM`, resulting in unclosed connections and abrupt termination of in-flight updates.
- Fix direction: Register a `signal.SIGTERM` handler on the event loop in `_run_polling()` to cancel the polling task and permit orderly cleanup.

### [LOW] Core Logging Module is an Empty Unimplemented Stub
- File: `src/instavault/core/logging.py`
- Line(s): 1
- Category: Style / Maintainability
- What's wrong: `src/instavault/core/logging.py` is an empty 0-byte file that is never populated or imported across the codebase, while logging setup is hardcoded in `__main__.py:49-55`.
- Why it matters: Misleads developers expecting centralized logging configurations, resulting in inconsistent logging setups across different entry points and scripts.
- Fix direction: Move centralized logging configuration from `__main__.py` into `core/logging.py` or delete the empty stub.

### [LOW] Silent Discarding of Malformed ADMIN_IDS Entries
- File: `src/instavault/core/config.py`
- Line(s): 45-47
- Category: Config / Startup
- What's wrong: The comprehension parsing `ADMIN_IDS` filters with `if x.strip().isdigit()`, silently skipping any non-digit token without logging a warning or raising a configuration error.
- Why it matters: A typo in `.env` (such as `ADMIN_IDS=1234567, 890123a`) silently drops the affected user ID, locking out the intended administrator with zero diagnostic feedback in startup logs.
- Fix direction: Log a warning or raise a configuration validation error when invalid tokens are detected in `ADMIN_IDS`.

### [NEEDS-CONFIRMATION] Hardcoded Mystery Box Reward Parameters Diverge from rewards.py Constants
- File: `src/instavault/constants/rewards.py`
- Line(s): 9-10
- Category: Business Parameters / Unreviewed Logic
- What's wrong: `rewards.py` explicitly defines `MYSTERY_BOX_MIN = 25` and `MYSTERY_BOX_MAX = 2000`. However, the daily slot machine implementation in `handlers/main_menu.py:398-401` completely ignores these constants and hardcodes `_SLOT_WIN_MIN = 60`, `_SLOT_WIN_MAX = 100`, `_SLOT_LOSE_MIN = 30`, and `_SLOT_LOSE_MAX = 60`.
- Why it matters: The centralized economy parameters (allowing up to 2,000 Sparks) are overridden by narrow, unreviewed hardcoded values (capped at 100 Sparks). Needs confirmation on whether the slot machine is intended to follow `rewards.py` or maintain a distinct reward table.
- Fix direction: Clarify the canonical economy parameters for Mystery Box / Slot Machine and import them from `rewards.py`.

### [NEEDS-CONFIRMATION] Orphaned Business Constants in rewards.py Without Codebase Implementation
- File: `src/instavault/constants/rewards.py`
- Line(s): 3, 4, 11, 16, 19, 20, 21, 25, 27, 28
- Category: Business Parameters / Unreviewed Logic
- What's wrong: `rewards.py` defines multiple business rules and thresholds that have no corresponding logic or references anywhere in `src/instavault`:
  - `VIP_SLOTS = 1000`: Standing Priority 2 addresses the VIP founding-member cap race condition; however, `VIP_SLOTS` is completely unreferenced in the codebase. Users are created with `is_vip_member: False` and VIP is only manually toggled by admins in `user_control.py`. There is no automated VIP signup logic or cap enforcement at all.
  - `DELIVERY_PROMISE_MINUTES = 45`, `COMPENSATION_TRIGGER_MINUTES = 60`, `COMPENSATION_AMOUNT = 200`: No delivery monitoring or automatic compensation job exists in the codebase.
  - `PASSIVE_PERCENT = 5`, `PASSIVE_MONTHLY_CAP = 500`, `REFERRAL_MISSION_BONUS = 300`: No passive referral commission or mission bonus is tracked or awarded.
  - `SPARK_EXPIRY_DAYS = 90`: No spark expiration cleanup logic exists.
  - `DAILY_MISSION_REWARD = 400`, `AD_WATCH_REWARD = 150`: Unimplemented reward sources.
- Why it matters: Indicates either incomplete specification implementation or dead constants from earlier agent generations. Features advertised to users or planned in specifications (like VIP founding caps or late-delivery compensations) do not operate in practice.
- Fix direction: Confirm product specifications for VIP cap, order compensation, and passive referral features, and implement or remove the unused constants.

---

## Phase 2 — Database & persistence

### [CRITICAL] Order Cancellation and Refund Corrupts Lifetime Sparks and Leaderboard (Double-Count Exploit)
- File: `src/instavault/database/db_manager.py`
- Line(s): 771-773
- Category: Concurrency / Data Corruption / Reward Abuse
- What's wrong: In `cancel_order_and_refund`, refunded Sparks are credited using `await increment_spark_balance(user_id, sparks)`. That function increments both `spark_balance` and `lifetime_sparks`. When placing an order (`place_order_transactional`), only `spark_balance` is deducted, while `lifetime_sparks` (the permanent ranking metric) remains unchanged.
- Why it matters: Users can repeatedly place orders and have an admin cancel/refund them to artificially inflate `lifetime_sparks` without spending or earning any net Sparks, permanently corrupting the leaderboard and user rank tier.
- Fix direction: Use a dedicated refund function that increments only `spark_balance` without modifying `lifetime_sparks`.

### [CRITICAL] Non-Transactional Multi-Step Order Refund Can Permanently Destroy Sparks on Failure
- File: `src/instavault/database/db_manager.py`
- Line(s): 744-785
- Category: Database / Concurrency / Error Handling
- What's wrong: `cancel_order_and_refund` is explicitly non-transactional. It first updates the order status to `"cancelled"` in Firestore, and subsequently attempts `increment_spark_balance`, `log_transaction`, and `delete_link_lock` as separate, uncoordinated operations.
- Why it matters: If `order_ref.update` succeeds but a network error, timeout, or process crash interrupts execution before `increment_spark_balance`, the order is marked `cancelled` but Sparks are never refunded. Any retry by an admin is rejected (`if order_data.get("status") != "pending_approval": raise ValueError`), permanently locking the user out of their spent Sparks and leaving the link lock stuck forever.
- Fix direction: Wrap order status update, balance refund, ledger logging, and link lock release inside an atomic `@async_transactional` Firestore transaction.

### [CRITICAL] Missing Transactions on Shortener and Quiz Task Completions (Standing Priority 1 & 3)
- File: `src/instavault/database/db_manager.py`
- Line(s): 1143-1181, 1183-1216
- Category: Race Condition / Concurrency / Reward Abuse
- What's wrong: Neither `complete_shortener_task()` nor `complete_quiz_task()` is wrapped in an atomic Firestore transaction. Neither verifies inside a transaction whether `last_shortener_task_date` or `last_quiz_date` has already been set for today.
- Why it matters: If two callback queries or webhook completions arrive simultaneously (e.g. network latency jitter, rapid double-tap, or replayed callback requests), both will execute `update({"spark_balance": Increment(reward), ...})`, crediting double rewards (1,000 Sparks instead of 500 Sparks) to the user's account.
- Fix direction: Wrap task completion in an `@async_transactional` function that reads the user document and atomically validates cooldown before incrementing balances.

### [HIGH] Redis Cache Datetime Serialization Bypasses Daily Cooldowns in Downstream Services
- File: `src/instavault/database/redis_manager.py` & `src/instavault/database/db_manager.py`
- Line(s): `src/instavault/database/redis_manager.py:91-125`, `src/instavault/database/db_manager.py:101-122`
- Category: Concurrency / Data Validation / Logic
- What's wrong: When `get_user` caches user documents in Redis, datetime objects (such as `last_coin_flip_date`, `created_at`, `last_daily_reset`) are serialized to ISO strings via `_DateTimeEncoder`. On cache hits, `json.loads()` returns raw strings instead of `datetime` objects.
- Why it matters: Downstream services that inspect datetime fields via `hasattr(field, "date")` or `isinstance(field, date)` (such as `services/games_engine.py:121-131` for Coin Flip eligibility) fail their type checks on cache hits, falling back to `None`. This causes the cooldown check to falsely report that the user has not played today, allowing users to play infinite free games and drain Sparks.
- Fix direction: Parse ISO date strings back into datetime objects when reading from cache in `get_cached_user_data()` or standardize date serialization across the database layer.

### [HIGH] Deduct Spark Balance Permits Negative Balances (No Floor Guard)
- File: `src/instavault/database/db_manager.py`
- Line(s): 159-168
- Category: Logic / Concurrency
- What's wrong: `deduct_spark_balance` unconditionally applies `Increment(-amount)` to the user's Firestore document without checking if the current balance is greater than or equal to `amount`.
- Why it matters: If an admin or background service calls `deduct_spark_balance` on a user with fewer Sparks than `amount`, the balance becomes negative (e.g. -100 Sparks), corrupting the user's account state and breaking balance invariants.
- Fix direction: Wrap balance deduction in a transaction or check that `spark_balance >= amount` before applying the decrement.

### [HIGH] Unhandled Fire-and-Forget Task in User Creation
- File: `src/instavault/database/db_manager.py`
- Line(s): 364-366
- Category: Async Correctness / Concurrency
- What's wrong: In `create_user_transactional`, `asyncio.create_task(record_new_account(user_id))` is spawned as a fire-and-forget background task without retaining a strong reference or awaiting it.
- Why it matters: Under Python 3.8+, unreferenced asyncio tasks can be garbage-collected mid-execution before completion. If garbage-collected or if the event loop shuts down, the user signup is never recorded in the Redis analytics set, distorting daily signup counts and admin analytics.
- Fix direction: Await `record_new_account(user_id)` directly since `create_user_transactional` is already an async coroutine.

### [HIGH] Lack of Self-Referral Prevention at the Database Layer (Standing Priority 1 & Reward Abuse)
- File: `src/instavault/database/db_manager.py`
- Line(s): 257-261, 290-315
- Category: Reward Abuse / Concurrency
- What's wrong: `_create_user_tx` and `create_user_transactional` do not verify whether `referrer_uid == str(user_id)`.
- Why it matters: If a caller passes the user's own ID as `referrer_uid`, the transaction awards both the referee bonus (`+400`) and the referrer join bonus (`+500`) to the same account, granting 1,200 Sparks instead of the standard 300 welcome bonus.
- Fix direction: Add an explicit guard `if referrer_uid and str(referrer_uid) != str(user_id):` in `_create_user_tx`.

### [MEDIUM] Permanent Link Lockout on Unhandled Order Failures or Non-Normalized URLs
- File: `src/instavault/database/db_manager.py`
- Line(s): 622-630, 677-685, 716-726
- Category: Concurrency / State Leak
- What's wrong: `place_order_transactional` creates a lock in `active_link_locks` with ID `md5(instagram_url)`. Locks have no TTL or expiry timestamp. Furthermore, URLs are hashed as raw strings without normalization (case, query parameters, trailing slashes).
- Why it matters: If an order fails externally, gets stuck, or is terminated without reaching `delete_link_lock()`, the Instagram URL remains locked indefinitely, permanently preventing any user from ordering views for that URL. Minor URL variations also generate different MD5 hashes, bypassing concurrent order protection.
- Fix direction: Add a TTL or expiration timestamp to link lock documents, normalize URLs before hashing, and implement an automatic stale-lock cleanup mechanism.

### [MEDIUM] Leaderboard Cache Polluted by Queries with Lower Limits
- File: `src/instavault/database/db_manager.py`
- Line(s): 427, 446-467
- Category: Logic / Data Validation
- What's wrong: `get_leaderboard(limit)` caches Firestore query results directly under the static Redis key `"leaderboard:lifetime"` for 900 seconds. If called with `limit=5`, it writes a 5-element list to `"leaderboard:lifetime"`.
- Why it matters: Subsequent calls requesting `limit=10` will read the cached 5-element list and return only 5 items, truncating the leaderboard for all users until the cache expires 15 minutes later.
- Fix direction: Include `limit` in the cache key (e.g. `f"leaderboard:lifetime:{limit}"`) or always fetch and cache a canonical top-N list (e.g. top 50).

### [MEDIUM] update_user Swallows All Exceptions and Falsely Assumes Non-Existent User
- File: `src/instavault/database/db_manager.py`
- Line(s): 124-132
- Category: Error Handling
- What's wrong: `update_user` wraps `await db.collection(USERS_COL).document(str(user_id)).update(fields)` in `try...except Exception as e:`, logs `"Attempted to update non-existent user"`, and silently swallows the error.
- Why it matters: Network timeouts, quota limits, or permission errors are silently masked. Calling code (such as admin balance updates in `user_control.py:1157` or Instagram handle linking in `main_menu.py:929`) believes the database update succeeded, giving false positive confirmations to users and administrators.
- Fix direction: Re-raise or catch specific `NotFound` exceptions, and let transient infrastructure exceptions propagate so callers can handle or retry failures.

### [MEDIUM] Inefficient Double Aggregation Query on Zero Today Accounts
- File: `src/instavault/database/db_manager.py`
- Line(s): 1103-1115, 1128-1135
- Category: Performance / Database
- What's wrong: In `get_today_new_accounts_count_firestore`, the code checks `if results and results[0] and int(results[0][0].value) > 0:`. If the count is 0, it treats it as a failure and executes a second aggregation query on `join_date`. Furthermore, `get_today_new_accounts_count()` falls back to Firestore whenever Redis count is 0 (`if redis_count > 0:`).
- Why it matters: Whenever zero new users have joined today (e.g. early morning or quiet periods), every admin dashboard check triggers two redundant Firestore aggregation queries instead of returning 0, increasing database latency and billing costs.
- Fix direction: Check `if results and results[0]: return int(results[0][0].value)` without requiring `> 0`, and distinguish between a Redis cache miss and a genuine count of 0.

### [LOW] Ban and Unban Functions Do Not Invalidate In-Memory Ban Cache
- File: `src/instavault/database/db_manager.py`
- Line(s): 1046-1060
- Category: Architecture / Maintainability
- What's wrong: `ban_user()` and `unban_user()` only update Firestore and invalidate the user Redis cache; they do not call `add_to_ban_cache()` or `remove_from_ban_cache()` in `middlewares/ban_check.py`.
- Why it matters: Handlers must remember to manually update the in-memory ban cache after calling `ban_user`/`unban_user`. Any code calling `ban_user` directly without the secondary call leaves the user unbanned in the active bot instance until reboot.
- Fix direction: Encapsulate `add_to_ban_cache` and `remove_from_ban_cache` directly within `ban_user()` and `unban_user()`.

### [LOW] Firestore AsyncClient Never Cleanly Closed on Shutdown
- File: `src/instavault/database/firebase_init.py`
- Line(s): 10, 42-44
- Category: Resources
- What's wrong: `firebase_init.py` instantiates `firestore_async.client()` stored in `_db`, but does not provide a `close_firebase()` function to close active gRPC channels on application shutdown.
- Why it matters: When the bot process stops, active gRPC channels and thread pools are terminated abruptly without closing TCP connections.
- Fix direction: Add a `close_firebase()` helper that calls `await _db.close()` and invoke it in `__main__.py` shutdown hooks.

### [NEEDS-CONFIRMATION] Dead/Unused Waitlist Code and Unimplemented VIP Cap System
- File: `src/instavault/database/db_manager.py`
- Line(s): 19, 60, 226, 228, 965-1000
- Category: Business Parameters / Unreviewed Logic
- What's wrong: `db_manager.py` defines `WAITLIST_COL = "waitlist"`, default fields `"waitlist_pos": None` and `"is_vip_member": False`, and helper functions `add_to_waitlist`, `get_waitlist_entry`, `update_waitlist_entry`, and `activate_waitlist_user`. However, none of these functions are called anywhere in the bot, and `create_user_transactional` has no logic to assign VIP status or enforce the 1,000-member VIP founding cap.
- Why it matters: Clarifies Standing Priority 2: the VIP founding-member cap race condition does not manifest because the entire VIP cap feature is unintegrated dead code in the database layer. Needs confirmation on whether pre-launch waitlist and VIP founding cap should be activated or removed.
- Fix direction: Confirm product requirements for the VIP founding-member cap and implement atomic cap incrementing in `_create_user_tx`, or deprecate the unused waitlist methods.

### [NEEDS-CONFIRMATION] Unused Dead Functions: reward_referrer and Orphaned User Fields
- File: `src/instavault/database/db_manager.py`
- Line(s): 203, 204, 223, 396-416
- Category: Business Parameters / Unreviewed Logic
- What's wrong:
  - `reward_referrer()` is defined at lines 396-416 as an un-transactional referral rewarding function, but is never called anywhere in the codebase (referral rewards are handled inside `_create_user_tx`).
  - In `_build_default_user_data`, `"rank_points": 0` and `"power_score": 0` are populated on every user document, but are never modified, calculated, or incremented by any function in the database layer.
- Why it matters: Dead code creates maintenance confusion and schema bloat; features like rank points or power score may have been planned but never implemented.
- Fix direction: Remove `reward_referrer()` or deprecate it, and confirm whether rank points and power scores should have active calculation engines.

---

## Phase 3 — Services / business logic

### [CRITICAL] Coin Flip Sparks Movement Lacks Atomic Firestore Transaction (Standing Priority 1)
- File: `src/instavault/services/games_engine.py`
- Line(s): 142-176
- Category: Race Condition / Concurrency / Reward Abuse
- What's wrong: In `process_coin_flip_result`, balance increment, transaction ledger logging, and cooldown update are executed as three separate, uncoordinated database calls (`increment_spark_balance`, `log_transaction`, `update_user`). Furthermore, `process_coin_flip_result` performs no atomic verification of `last_coin_flip_date` inside a transaction.
- Why it matters: Directly violates Standing Priority 1. If step 1 succeeds and step 3 fails (or if `update_user` swallows the exception), the user receives Sparks without entering cooldown. Rapid parallel requests can pass the pre-animation eligibility check and all invoke `process_coin_flip_result`, allowing players to multiply their daily earnings.
- Fix direction: Encapsulate the entire Coin Flip claim inside an `@async_transactional` Firestore transaction that verifies `last_coin_flip_date` before updating balances and writing the ledger entry.

### [CRITICAL] Redis Token Overwrite Allows Replay and Multiple Active Mission Claims (Standing Priority 3)
- File: `src/instavault/services/mission_token.py`
- Line(s): 44-47, 68-106, 129-134, 215-217
- Category: Concurrency / Race Condition / Reward Abuse
- What's wrong: In `create_token()`, `await redis.setex(f"{PENDING_PREFIX}{user_id}", ttl, token)` unconditionally overwrites the user's pending token without deleting or invalidating the previous token stored under `task:shortener:<token>`. The same flaw exists in `create_quiz_token()` and `create_verify_token()`.
- Why it matters: Directly violates Standing Priority 3. If a user triggers token creation twice (via multiple devices, rapid button taps, or waiting between sessions), both generated tokens remain valid in Redis simultaneously. Since `verify_and_consume()` only deletes the specific token key and clears `pending`, both tokens can be redeemed in sequence, awarding duplicate CPA shortener rewards (500 + 500 = 1,000 Sparks).
- Fix direction: Invalidate the previous token key before creating a new one, or use Redis `SETNX` on the pending key to reject token generation while an unconsumed token is active.

### [HIGH] Coin Flip Cooldown Completely Ineffective on Cache Hits
- File: `src/instavault/services/games_engine.py`
- Line(s): 118-137
- Category: Logic / Concurrency / Reward Abuse
- What's wrong: In `check_coin_flip_eligibility`, `last_flip` is extracted from `user_data.get("last_coin_flip_date")`. When retrieved from the Redis cache, it is an ISO string (`str`). The function checks `hasattr(last_flip, "date")` and `isinstance(last_flip, date)`, both of which evaluate to `False` for strings, falling back to `last_flip_date = None`.
- Why it matters: As a consequence of the cache serialization bug identified in Phase 2, whenever user data is served from Redis (cache hit), the cooldown check evaluates `last_flip_date == today_ist` as `False`, reporting the user as "Eligible". Users can play unlimited Coin Flips and drain the bot's economy until the Redis cache key expires.
- Fix direction: Parse ISO string timestamps into `date` objects in `check_coin_flip_eligibility` when `isinstance(last_flip, str)`.

### [HIGH] SMM API Request Lacks HTTP Status Code Validation and Crashes on Panel Outages
- File: `src/instavault/services/smm_api.py`
- Line(s): 66-78
- Category: Error Handling
- What's wrong: `_api_request()` executes `data = await resp.json(content_type=None)` without first checking `resp.status == 200`.
- Why it matters: When an external SMM reseller panel experiences downtime, Cloudflare challenges, maintenance (502/503), or rate limits (429), it returns HTML error bodies (`<!DOCTYPE html>`). Calling `.json()` fails with JSONDecodeError, masking the real HTTP status and response message behind a confusing "Expecting value: line 1 column 1" error, preventing proper automatic fallback or diagnostic logging.
- Fix direction: Check `resp.status != 200`, extract `await resp.text()`, and raise an informative `SMMApiError` with the status code and snippet.

### [MEDIUM] Check-Then-Act Race Condition in Mission Token Generation
- File: `src/instavault/services/mission_token.py`
- Line(s): 58-65
- Category: Concurrency / Race Condition
- What's wrong: `get_pending_token()` and `create_token()` are separate asynchronous calls.
- Why it matters: A user sending concurrent callback requests can pass the `get_pending_token() is None` check in parallel in both coroutines, creating duplicate active tokens and triggering parallel external shortener API calls.
- Fix direction: Combine pending check and token reservation into an atomic Redis Lua script or `SET NX`.

### [MEDIUM] Ephemeral ClientSession Created Per Request in External API Services
- File: `src/instavault/services/shortener_api.py` & `src/instavault/services/smm_api.py`
- Line(s): `src/instavault/services/shortener_api.py:53-54`, `src/instavault/services/smm_api.py:66-67`
- Category: Resources / Performance
- What's wrong: Both `create_short_link()` and `_api_request()` instantiate a brand new `aiohttp.ClientSession()` on every single HTTP call.
- Why it matters: Opening and closing a session per request disables HTTP keep-alive connection pooling, requiring a full TCP and TLS handshake for every single order placement, status check, or shortener link generated, increasing latency and socket consumption under load.
- Fix direction: Provide and reuse a shared or singleton `aiohttp.ClientSession` instance closed on bot shutdown.

### [LOW] Hardcoded Reward Multiplier and Inconsistent Reward Constants in games_engine.py
- File: `src/instavault/services/games_engine.py`
- Line(s): 100, 342
- Category: Business Parameters / Unreviewed Logic
- What's wrong: `COIN_FLIP_MULTIPLIER = 10` is hardcoded in `games_engine.py:100` and is completely absent from `constants/rewards.py`. Furthermore, `QUIZ_REWARD_AMOUNT = 250` is hardcoded in `games_engine.py:342` instead of being imported from `rewards.QUIZ_REWARD`.
- Why it matters: Centralized economy tuning through `constants/rewards.py` fails to update Coin Flip and Quiz rewards, causing economy configuration drift.
- Fix direction: Define `COIN_FLIP_MULTIPLIER` in `constants/rewards.py` and import both it and `QUIZ_REWARD` into `games_engine.py`.

### [LOW] Unhandled Firestore Exceptions in Transaction History Rendering
- File: `src/instavault/services/transaction_history.py`
- Line(s): 116, 135-139
- Category: Error Handling
- What's wrong: `render_transaction_page()` calls `count_user_transactions()` and `get_user_transactions()` with no `try...except` error guarding.
- Why it matters: If Firestore composite index `(user_id, created_at DESC)` is missing or if Firestore experiences connectivity issues, the exception unhandledly crashes the calling handler, resulting in a frozen UI with no user error alert.
- Fix direction: Wrap database queries in `try...except` and return a friendly error message or fallback page on query failure.

### [NEEDS-CONFIRMATION] Hardcoded Verify Token TTL Diverges from rewards.py Architecture
- File: `src/instavault/services/mission_token.py`
- Line(s): 202
- Category: Business Parameters / Unreviewed Logic
- What's wrong: `VERIFY_TOKEN_TTL = 1800` is hardcoded at line 202 in `mission_token.py` while other token TTLs (`SHORTENER_TOKEN_TTL`, `QUIZ_TOKEN_TTL`) are defined in `constants/rewards.py`.
- Why it matters: Modifying token lifetimes in `rewards.py` will not affect verification tokens, causing inconsistent token expiration policies.
- Fix direction: Import `VERIFY_TOKEN_TTL` from `constants/rewards.py`.

---

## Phase 4 — User-facing handlers

### [CRITICAL] Quiz Reward Bypass via Unvalidated Direct Claim Callback (Standing Priority 1 & 3)
- File: `src/instavault/handlers/games_hub.py`
- Line(s): 388-447
- Category: Concurrency / Logic / Reward Abuse
- What's wrong: The `quiz_claim` callback query handler does not verify that the user has answered any questions or completed the active quiz session. It only checks `last_quiz_date == today_str` and `pending_token`, then immediately invokes `create_quiz_token(user_id)`.
- Why it matters: Any user or script can directly send callback data `quiz_claim` without ever starting or answering the 3 trivia questions. They will receive a valid shortener verification link and can claim 250 Sparks daily while bypassing the gameplay requirement entirely.
- Fix direction: Store completed question counts in FSM or verify that a quiz session state indicates 3/3 correct answers before generating the quiz token.

### [CRITICAL] Empty URL Order Placement and Irreversible Spark Deduction on FSM State Expiration
- File: `src/instavault/handlers/orders.py`
- Line(s): 252-266
- Category: State Leak / Data Integrity / Error Handling
- What's wrong: In `cb_confirm_order`, `ig_url` is fetched from FSM state via `data.get("instagram_url", "")`. If the user's FSM state expired (TTL timeout) or the bot restarted between link entry and confirmation click, `ig_url` is an empty string `""`. The handler never validates that `ig_url` is non-empty before calling `place_order_transactional`.
- Why it matters: Because `place_order_transactional` does not check for an empty URL, the atomic transaction succeeds: the user's Sparks are deducted permanently, an order document with `instagram_url: ""` is committed to Firestore, and an unfulfillable order alert is pushed to the admin panel with no recovery mechanism.
- Fix direction: Add an explicit guard `if not ig_url: await query.message.edit_text("⚠️ Session expired..."); return` in `cb_confirm_order` before invoking `place_order_transactional`.

### [HIGH] Unrouted Verify Token (`vf_`) Deep-Links Trap Users in Navigation Dead End
- File: `src/instavault/handlers/start.py` & `src/instavault/handlers/games_hub.py`
- Line(s): `src/instavault/handlers/start.py:85-108`, `src/instavault/handlers/games_hub.py:557-590`
- Category: Logic / Routing
- What's wrong: When a user hits their daily game limit, `_show_verify_human_screen` generates a `vf_` token and routes the user through GPLinks. However, `cmd_start` in `start.py` only checks for `sl_` and `qz_` prefixes, completely omitting the `vf_` prefix.
- Why it matters: Returning users completing the "Verify You're Human" flow re-enter the bot via `/start vf_...`, which falls through unrecognized and dumps them straight onto the dashboard. `handle_verify_deeplink` is never invoked, the verify token is never consumed, and the user never sees their verification success screen.
- Fix direction: Add `if deep_arg.startswith("vf_"): await handle_verify_deeplink(message, user_id, deep_arg); return` in `handlers/start.py:cmd_start`.

### [HIGH] Daily Slot Machine Permanent Lockout and Unbounded In-Memory Leak
- File: `src/instavault/handlers/main_menu.py`
- Line(s): 403-464
- Category: Concurrency / State Leak
- What's wrong: Daily slot spins are tracked in a global in-memory dictionary `_slot_sessions: dict[int, int] = {}`. In `cb_daily_slot_machine`, new attempts are initialized only `if user_id not in _slot_sessions:`. If a user spins once or twice on Day 1 and does not exhaust all 3 tries, on Day 2 `user_id not in _slot_sessions` evaluates to `False`, locking them to their leftover tries. If `tries_left` reaches 0 or an unhandled exception prevents cleanup, the user is permanently locked out on all future days until the bot process reboots.
- Why it matters: Users are permanently blocked from daily rewards, and `_slot_sessions` grows indefinitely in process memory with no TTL or eviction strategy.
- Fix direction: Track daily slot attempts in Redis with a midnight IST expiration, or include the date in the session key (e.g. `(user_id, today_str)`).

### [HIGH] Multi-Spin Race Condition During 3-4 Second Animated Dice Delays (Standing Priority 1)
- File: `src/instavault/handlers/games_hub.py` & `src/instavault/handlers/main_menu.py`
- Line(s): `src/instavault/handlers/games_hub.py:212-220`, `src/instavault/handlers/main_menu.py:478-487`
- Category: Concurrency / Race Condition / Reward Abuse
- What's wrong: In `cb_coin_flip`, `await asyncio.sleep(4)` occurs between checking eligibility and invoking `process_coin_flip_result`. In `cb_daily_slot_machine`, `await asyncio.sleep(3)` occurs before decrementing `_slot_sessions[user_id] = tries_left - 1`.
- Why it matters: Neither handler establishes a temporary lock or reservation flag during the animation delay. Rapid clicking or parallel callback requests enter while the user still appears eligible, allowing users to roll dice multiple times simultaneously, bypass daily limits, and claim multiple rewards.
- Fix direction: Set an in-flight processing lock in Redis before sending the dice animation, and release/finalize it after reward processing.

### [MEDIUM] Dangling FSM States Trap Users into Intercepting Future Text Messages
- File: `src/instavault/handlers/orders.py` & `src/instavault/handlers/main_menu.py`
- Line(s): `src/instavault/handlers/orders.py:214-226, 336-346`, `src/instavault/handlers/main_menu.py:874-939`
- Category: Logic / State Leak
- What's wrong:
  1. In `orders.py`, `handle_order_link` updates URL data and presents the confirmation keyboard without transitioning away from `OrderState.waiting_for_link`. Additionally, `cb_cancel_order` does not receive `state: FSMContext` and never calls `state.clear()`.
  2. In `main_menu.py`, `action_link_ig` sets `ProfileState.waiting_for_ig_handle`. Navigation callbacks (`go_dashboard`, `nav_order`, `nav_rewards`, `nav_profile`) do not clear FSM state.
- Why it matters: Users who navigate away or cancel an order/linking flow remain trapped in the FSM state. Any subsequent text message they send is intercepted as an Instagram link or handle, causing unexpected errors and overwriting database profiles.
- Fix direction: Explicitly clear or advance FSM state in confirmation steps and in all global navigation and cancel callbacks.

### [MEDIUM] Broken Referral Deep-Links when BOT_USERNAME Unset in Configuration
- File: `src/instavault/handlers/referrals.py` & `src/instavault/handlers/start.py`
- Line(s): `src/instavault/handlers/referrals.py:39`, `src/instavault/handlers/start.py:351`
- Category: Configuration / Logic
- What's wrong: Deep-links are constructed as `f"https://t.me/{config.BOT_USERNAME}?start={referral_code}"` without a fallback to `(await bot.get_me()).username`.
- Why it matters: If `BOT_USERNAME` is empty in `.env`, the bot outputs `https://t.me/?start=ref_...`, an invalid link that fails to open the bot on Telegram, crippling organic user referral growth.
- Fix direction: Fall back to `(await message.bot.get_me()).username` if `config.BOT_USERNAME` is blank, matching the pattern in `main_menu.py`.

### [MEDIUM] Overly Permissive IG Handle Sanitizer Extracts Path Segments from Post/Reel URLs
- File: `src/instavault/handlers/main_menu.py`
- Line(s): 89-97
- Category: Logic / Data Validation
- What's wrong: `_clean_ig_handle` strips `https://instagram.com/` and strips everything after the next slash. If a user pastes a post or reel URL (e.g. `https://instagram.com/reel/C8XYZ/` or `https://instagram.com/p/123/`), the sanitizer extracts `"reel"` or `"p"`.
- Why it matters: Because `"reel"` and `"p"` match `^[A-Za-z0-9._]{1,30}$`, the bot successfully saves `"reel"` or `"p"` as the user's official Instagram username.
- Fix direction: Explicitly reject URLs containing `/p/`, `/reel/`, `/reels/`, or `/tv/`, or validate that the path corresponds to a user profile rather than a media item.

### [LOW] Trivia Quiz Alerts Reveal Correct Answer on Failed Guess Without Penalty
- File: `src/instavault/handlers/games_hub.py`
- Line(s): 346-353
- Category: Logic / Business Logic
- What's wrong: When a player selects an incorrect answer in `cb_quiz_answer`, the popup alert displays `f"❌ Wrong! Correct answer: {correct_option}. Try again!"` and allows immediate re-selection of the revealed option.
- Why it matters: Eliminates all challenge and skill from the trivia game, enabling automated or brute-force taps to guarantee rewards with zero penalty or question regeneration.
- Fix direction: Mask the correct answer in the failure popup and either shuffle questions or impose a cooldown on incorrect answers.

### [LOW] Cosmetic URL Formatting Bug Prepending At-Symbol to Full URLs in Order History
- File: `src/instavault/handlers/main_menu.py`
- Line(s): 708
- Category: UI / Formatting
- What's wrong: In `_render_order_history`, the summary outputs `f"📸 IG Handle: @{ig}"` where `ig` is the raw `instagram_url` field from the order document.
- Why it matters: Results in malformed UI text such as `📸 IG Handle: @https://www.instagram.com/reel/C8...`, giving an unpolished look.
- Fix direction: Display `🔗 Link: {ig}` or sanitize the URL to extract the handle or post ID for display.

### [LOW] Unbounded Memory and Unsynchronized Recurrent Coroutines in Sports Arcade
- File: `src/instavault/handlers/games_dummy.py`
- Line(s): 21-23, 275-343
- Category: Resources / Concurrency
- What's wrong: `_play_penalty_round` is a recursive async coroutine that takes ~21 seconds to complete. If a user triggers a rematch or leaves mid-match, concurrent recursive instances mutate the same `PENALTY_SESSIONS[user_id]` entry. Furthermore, completed sessions are never removed via `pop()`.
- Why it matters: Causes memory leaks and broken animations/game states if accessed by users (registered in `__main__.py` under `/sports`).
- Fix direction: Clean up `PENALTY_SESSIONS.pop(user_id, None)` when `round > 3` and cancel active async tasks before starting a new round.

### [NEEDS-CONFIRMATION] Phantom APK Task Reward Advertised Without Crediting Implementation
- File: `src/instavault/handlers/main_menu.py` & `src/instavault/keyboards/inline.py`
- Line(s): `src/instavault/handlers/main_menu.py:834-867`, `src/instavault/keyboards/inline.py:186`
- Category: Business Parameters / Unreviewed Logic
- What's wrong: `mission_center_keyboard()` and the Mission screen advertise `⬇️ InstaVault App (400 Sparks)`. However, `cb_action_download_apk` only sends the `.apk` file (if `APK_FILE_ID` is set) and neither records task completion nor awards the 400 Sparks.
- Why it matters: Users download the app expecting 400 Sparks and receive nothing, generating support complaints and trust erosion. Needs confirmation on how APK installation should be verified and credited.
- Fix direction: Clarify verification mechanism (e.g. app server webhook, client telemetry, or manual admin approval) and implement the corresponding reward crediting logic.

---

## Phase 5 — Admin handlers (security-sensitive)

### [CRITICAL] Double-Fulfillment Race Condition in Order Approval Calling External SMM API (Standing Priority 1)
- File: `src/instavault/handlers/admin/order_approvals.py`
- Line(s): 168-233
- Category: Concurrency / Race Condition / Financial Loss
- What's wrong: In `cb_admin_approve`, the handler checks `if order_data.get("status") != "pending_approval":` and immediately calls `await smm_place_order(...)` before updating the status in Firestore (`await update_order_status(..., status="processing")`).
- Why it matters: If two admins click "Approve" simultaneously, or if an admin double-taps the button, both coroutines read status `"pending_approval"` before either updates Firestore. Both execute `smm_place_order()`, causing duplicate paid order placements on the external SMM reseller panel and spending real funds twice for a single order.
- Fix direction: Wrap status transition in an atomic transaction or acquire an atomic lock (e.g. status transition from `pending_approval` -> `approving` via Firestore transaction) before calling `smm_place_order()`.

### [CRITICAL] Admin Manual Spark Modifications Lack Atomic Firestore Transactions (Standing Priority 1)
- File: `src/instavault/handlers/admin/user_control.py`
- Line(s): 864-865, 1016-1019, 1157-1161
- Category: Concurrency / Race Condition / Standing Priority 1
- What's wrong: In `user_control.py`, `cb_confirm_add`, `cb_confirm_deduct`, and `cb_confirm_set` perform balance updates and ledger logging (`log_transaction`) as separate, uncoordinated operations outside a Firestore transaction. Furthermore:
  - `cb_confirm_deduct` reads `current = int(user_data.get("spark_balance", 0))` and checks `if current < amount`, then issues a non-transactional decrement. If the user spends Sparks between check and deduction, their balance goes negative.
  - `cb_confirm_set` calculates `delta = abs(new_amount - old_balance)` and calls `update_user` with a hardcoded `spark_balance: new_amount`. If any concurrent transactions (order placement, mission claim) occurred, their balance changes are blindly overwritten, and the transaction ledger logs an incorrect delta.
- Why it matters: Directly violates Standing Priority 1. Ledger and balance can desynchronize, and concurrent user activity causes data loss or corrupted balances.
- Fix direction: Wrap Add, Deduct, and Set balance operations inside `@async_transactional` Firestore functions that atomically check balances, mutate `spark_balance`, and append ledger entries.

### [HIGH] Ephemeral Scheduled Cron Broadcasts Lost on Process Restart
- File: `src/instavault/handlers/admin/broadcast.py`
- Line(s): 330-370
- Category: Concurrency / Availability / State Loss
- What's wrong: In `cb_confirm_cron_broadcast`, scheduled broadcasts (with delays up to 24 hours) are queued via `asyncio.create_task(run_scheduled_broadcast_task(...))` which simply calls `await asyncio.sleep(delay_seconds)`.
- Why it matters: The task lives strictly in process memory. Any server reboot, deployment, auto-scaling event, or container restart terminates the coroutine without warning. The scheduled broadcast is silently dropped, never delivers, and no failure alert is sent to the admin.
- Fix direction: Persist scheduled broadcasts to Firestore or Redis with scheduled execution timestamps, and process them via a persistent scheduler or cron worker.

### [HIGH] Missing User Authorization in Order Approval Handlers
- File: `src/instavault/handlers/admin/order_approvals.py`
- Line(s): 101-106, 119-123, 174-178
- Category: Security / Access Control
- What's wrong: `_verify_admin_group(query)` only validates `query.message.chat.id == config.ADMIN_GROUP_ID`. It never validates `query.from_user.id in config.ADMIN_IDS`.
- Why it matters: Any regular user who is a member of the admin group (e.g. non-admin team members, interns, support personnel, or users in test groups) can approve orders, trigger paid SMM API calls, or cancel orders and refund arbitrary Sparks to accounts.
- Fix direction: Verify both `query.message.chat.id == config.ADMIN_GROUP_ID` AND `query.from_user.id in config.ADMIN_IDS`.

### [HIGH] Synchronous Broadcast Loop in Callback Query Handler Lacking Concurrency Lock
- File: `src/instavault/handlers/admin/broadcast.py`
- Line(s): 539-644
- Category: Performance / Concurrency / Availability
- What's wrong: `cb_confirm_all_broadcast` runs the entire user delivery loop directly within the callback query handler across all users (`for target_uid in user_ids:` with `asyncio.sleep(0.04)`). For large user bases (e.g. 10,000+ users), this handler runs synchronously for 7 to 30+ minutes. Furthermore, there is no global `is_broadcasting` lock.
- Why it matters: Webhook requests will time out, causing Telegram to resend the update. If multiple admins click broadcast or if the button is triggered again, multiple broadcast loops run concurrently, doubling messages to every user and triggering Telegram rate limits.
- Fix direction: Offload the broadcast loop to a background task with an atomic Redis lock (`lock:broadcast`) and immediately update the admin message to "Broadcast Started".

### [MEDIUM] Total Views Delivered Never Incremented Across Codebase
- File: `src/instavault/handlers/admin/order_approvals.py` & `src/instavault/database/db_manager.py`
- Line(s): `src/instavault/handlers/admin/order_approvals.py:324-329`, `src/instavault/database/db_manager.py:218`
- Category: Logic / Data Integrity
- What's wrong: When an order is completed (`smm_status in ("completed", "complete")`), `update_order_status` marks the order completed, but `total_views_recv` on the user's Firestore document is never incremented.
- Why it matters: The field `total_views_recv` is permanently stuck at `0` for every user. Both the user's dashboard (`main_menu.py:128`) and the admin control center (`user_control.py:221`) will permanently display `Total Views: 0 delivered` regardless of how many orders were successfully delivered.
- Fix direction: In `order_approvals.py`, increment `total_views_recv` by `order_data["views_ordered"]` on the user document upon order completion.

### [MEDIUM] SMM API Failure Strips Inline Keyboard Trapping Admin
- File: `src/instavault/handlers/admin/order_approvals.py`
- Line(s): 221-225
- Category: UI / Error Handling
- What's wrong: When `smm_place_order` raises `SMMApiError`, `query.message.edit_text(...)` is called without passing `reply_markup`.
- Why it matters: Telegram Bot API strips the inline keyboard by default when `reply_markup` is omitted. Although the message text tells the admin *"Order still pending. Try again or Cancel."*, the `[✅ Approve]` and `[❌ Cancel]` buttons are completely removed, permanently stranding the order in `pending_approval` with no way for admins to approve or cancel it from the ticket.
- Fix direction: Pass `reply_markup=query.message.reply_markup` in `query.message.edit_text` so the action buttons remain accessible.

### [MEDIUM] Reset Fields Ineffective for Slot Machine and Incomplete for Other Games
- File: `src/instavault/handlers/admin/user_control.py`
- Line(s): 118-123, 1552
- Category: Logic / State Leak
- What's wrong: In `_RESET_FIELDS`, resetting `"mystery_box"` resets `last_mystery_box_date` in Firestore. However, because slot machine tries are stored in `_slot_sessions` in `main_menu.py` memory, resetting the Firestore field does not reset `_slot_sessions[user_id]`. If the user exhausted their tries, they remain locked out. Furthermore, `_RESET_FIELDS` lacks entries for `last_coin_flip_date`, `last_quiz_date`, and link penalty timeouts.
- Why it matters: Admin field resets fail to unblock locked users, giving admins a false confirmation that the user was reset.
- Fix direction: Clear `_slot_sessions` (or migrate slot sessions to Redis) upon reset, and add `last_coin_flip_date` and `last_quiz_date` to `_RESET_FIELDS`.

### [LOW] Duplicate Refund Alert Sent on Status Check of Already Cancelled Order
- File: `src/instavault/handlers/admin/order_approvals.py`
- Line(s): 360-388
- Category: Error Handling / Logic
- What's wrong: In `cb_admin_check_status`, if `smm_status` is cancelled, it calls `cancel_order_and_refund(order_id)`. If `ValueError` ("Already cancelled") is raised, the `except ValueError:` block simply passes, and execution falls through to send a refund notification to the user.
- Why it matters: Users receive misleading duplicate notifications stating their order was refunded, even if the refund was already processed previously.
- Fix direction: Return immediately inside the `except ValueError:` block without sending a duplicate DM.

### [LOW] Unhandled ValueError in Ban Cache Metrics on Non-Numeric UID
- File: `src/instavault/handlers/admin/bot_status.py`
- Line(s): 129
- Category: Error Handling
- What's wrong: In `cb_admin_bot_status`, `banned_uids = {uid for uid in BANNED_USER_CACHE if int(uid) not in config.ADMIN_IDS}` assumes all cached IDs are integer strings.
- Why it matters: If any non-integer key is placed into `BANNED_USER_CACHE` (e.g. from tests or prefix formatting), `int(uid)` raises `ValueError` and crashes the entire bot status screen. Additionally, line 157 hardcodes `(Polling Mode)` regardless of whether the bot is running in Webhook mode.
- Fix direction: Guard with `uid.isdigit()` before casting to int, and inspect `config.USE_WEBHOOK` for telemetry.

### [NEEDS-CONFIRMATION] Ephemeral Runtime Mutation of APK_FILE_ID via set_key in Cloud Containers
- File: `src/instavault/handlers/admin/dashboard.py`
- Line(s): 392-396
- Category: Architecture / Configuration
- What's wrong: In `cb_apk_confirm`, the uploaded APK file ID is saved using `set_key(".env", "APK_FILE_ID", file_id)` and assigned to `config.APK_FILE_ID`. In ephemeral cloud container environments (Docker, Render, Kubernetes), write access to `.env` is either forbidden or wiped upon container restart. Furthermore, other running worker processes never receive the updated ID.
- Why it matters: Admin APK updates may fail silently, be lost on container restart, or cause multi-worker inconsistencies. Needs confirmation on whether `APK_FILE_ID` should be persisted in Firestore or Redis.
- Fix direction: Persist `APK_FILE_ID` in Firestore or Redis so all workers dynamically fetch the active APK file ID.

---

## Phase 6 — Middleware, filters, keyboards, lexicon, utils

### [CRITICAL] FSMResetMiddleware Destroys Active Onboarding Session on Normal Navigation
- File: `src/instavault/middlewares/fsm_reset.py` & `src/instavault/handlers/start.py`
- Line(s): `src/instavault/middlewares/fsm_reset.py:44-51`, `src/instavault/handlers/start.py:121-127, 226-233`
- Category: Logic / State Leak
- What's wrong: `FSMResetMiddleware` sets `should_clear = True` whenever callback data starts with `"ob_"` (`or cb.startswith("ob_")`). However, `ob_beat_2`, `ob_how_it_works`, and `ob_beat_3` are the legitimate callback queries used in the 3-beat onboarding flow while `OnboardingState.in_progress` is active.
- Why it matters: As soon as a newly onboarding user taps "Get Free Views Now" (`ob_beat_2:...`), `FSMResetMiddleware` clears their FSM state. When the user reaches Beat 3 (`cb_beat_3`), `await state.get_data()` returns an empty dictionary. All onboarding session metadata (`start_ts`, `username`, `first_name`) is prematurely wiped out during the normal onboarding flow.
- Fix direction: Remove `or cb.startswith("ob_")` from `FSMResetMiddleware`, or skip clearing if the active state belongs to `OnboardingState`.

### [HIGH] CleanChatMiddleware Silently Deletes All Admin Messages in Private Chats
- File: `src/instavault/middlewares/clean_chat.py`
- Line(s): 24, 44-78
- Category: Logic / Implementation Omission
- What's wrong: `CleanChatMiddleware` imports `from instavault.core.config import ADMIN_IDS` at line 24 and declares in its module docstring that *"Admin messages are exempt (admins can debug and manage without deletion)"*. However, the middleware never actually checks `if user_id in ADMIN_IDS:`.
- Why it matters: All incoming messages from administrators in private chats (e.g. `/admin`, User IDs typed in search, balance adjustments, direct message copy) are deleted immediately in the `finally:` block. Furthermore, admin file uploads in `ApkUploadState.waiting_for_file` are not exempted (exemptions only check `"waiting_for_content"` and `"content_input"`), causing uploaded APK documents to be deleted.
- Fix direction: Insert `if user_id in ADMIN_IDS: return await handler(event, data)` before processing deletions.

### [HIGH] Unhandled Inline Query Mode Leaves "Share My Link" Non-Functional
- File: `src/instavault/keyboards/inline.py`
- Line(s): 395-410
- Category: Feature Incomplete / Telegram API
- What's wrong: In `referral_keyboard()`, the "Share My Link" button uses `switch_inline_query=share_text`. In Telegram, `switch_inline_query` triggers an Inline Query (`@InstaVaultBot <share_text>`). However, the codebase contains zero `@router.inline_query` handlers, and inline mode is not implemented.
- Why it matters: When users tap "Share My Link", Telegram opens chat selection and activates inline query mode, but the bot returns no results (spinning loader or "No results found"). Users are completely unable to share their referral links through this button, breaking viral acquisition.
- Fix direction: Change `switch_inline_query` to a standard URL button using `https://t.me/share/url?url={share_link}&text={share_text}`, or implement an `@router.inline_query` handler.

### [MEDIUM] ThrottlingMiddleware Freezes Client UI on Micro-Throttled Callback Queries
- File: `src/instavault/middlewares/throttling.py`
- Line(s): 82-98
- Category: UI / Error Handling
- What's wrong: When a user triggers any callback query within 0.5s of a prior event, `ThrottlingMiddleware` drops the event by returning `None` (`if now - self._users.get(key, 0.0) < cooldown_to_apply: return None`) without calling `await event.answer()`.
- Why it matters: Unanswered callback queries leave the inline button's loading spinner spinning indefinitely on the Telegram client (up to 30-60 seconds) until client-side timeout, giving users the impression that the bot is frozen or unresponsive.
- Fix direction: Call `await event.answer("⏳ Please slow down!", show_alert=False)` before returning `None` when throttling a `CallbackQuery`.

### [MEDIUM] CleanChatMiddleware Deletes User Input on Validation Failures Preventing Copy/Edit
- File: `src/instavault/middlewares/clean_chat.py`
- Line(s): 56-78
- Category: UX / Logic
- What's wrong: `CleanChatMiddleware` executes `await bot.delete_message(...)` inside a `finally:` block regardless of whether handler validation succeeded or failed.
- Why it matters: When a user enters an invalid Instagram URL in `OrderState.waiting_for_link` (or an invalid IG username during profile linking), their message is immediately deleted. The user is told their link was invalid, but they cannot see the typo, copy, or edit the URL they just submitted.
- Fix direction: Only delete user messages on successful handler execution, or preserve failed messages during interactive FSM inputs.

### [MEDIUM] Naive Datetime Localized Directly to IST Distorts UTC Timestamps by 5.5 Hours
- File: `src/instavault/utils/helpers.py`
- Line(s): 40-43
- Category: Data Integrity / Timezone
- What's wrong: In `format_timestamp()`, if `dt.tzinfo is None`, the code executes `dt = tz.localize(dt)` where `tz = pytz.timezone(TIMEZONE)` (IST).
- Why it matters: Standard database systems (including Firestore server timestamps and UTC datetime objects) often return naive datetimes representing UTC. Directly localizing a naive UTC datetime with `tz.localize()` erroneously declares the UTC timestamp as IST, resulting in a -5 hour 30 minute time offset in all displayed order, join, and transaction timestamps.
- Fix direction: Treat naive datetimes as UTC first (`pytz.utc.localize(dt)`), then convert to IST via `.astimezone(tz)`.

### [LOW] FSMResetMiddleware Omits Standard Navigation Commands
- File: `src/instavault/middlewares/fsm_reset.py`
- Line(s): 34-37
- Category: Logic / State Leak
- What's wrong: For `Message` events, `FSMResetMiddleware` only checks `if text.startswith("/start"): should_clear = True`. It ignores all other primary navigation commands: `/dashboard`, `/mission`, `/order`, `/rewards`, `/profile`, `/help`, and `/admin`.
- Why it matters: If a user is trapped in an FSM state (such as `ProfileState.waiting_for_ig_handle` or `OrderState.waiting_for_link`) and sends `/dashboard` or `/profile`, the FSM state is not cleared, causing the user to remain trapped in the state.
- Fix direction: Expand the message check to clear state on all standard commands (`{"/start", "/dashboard", "/mission", "/order", "/rewards", "/profile", "/help", "/cancel", "/admin"}`).

### [NEEDS-CONFIRMATION] Unused and Inconsistent Rank Tier Engine in utils/helpers.py
- File: `src/instavault/utils/helpers.py`
- Line(s): 71-87
- Category: Business Parameters / Unreviewed Logic
- What's wrong: `helpers.py` defines `RANK_THRESHOLDS = {"rookie": 0, "rising": 500, "hustler": 2000, "elite": 6000, "vaultking": 15000}` and `get_rank_tier()`. This function is completely uncalled in the entire codebase. Furthermore, its tier names diverge from `constants/rewards.py:RANKS` (`Rookie`, `Bronze`, `Silver`, `Gold`, `Diamond`) and default database schemas (`Rookie Vaulter`).
- Why it matters: Confirms that rank progression logic is dead code spread across three conflicting naming schemes. Needs confirmation on whether the rank engine should be connected to `power_score` / `rank_points` or removed.
- Fix direction: Unify rank definitions across `rewards.py`, `db_manager.py`, and `helpers.py`, and invoke `get_rank_tier()` on point changes.

---

## Phase 7 — Misc / project-level / external services & root configs

### [CRITICAL] app_server Fails to Check Ban Status Allowing Banned Users to Authenticate and Use App Services
- File: `app_server/controllers/authController.ts` & `app_server/middlewares/authMiddleware.ts`
- Line(s): `app_server/controllers/authController.ts:34-41, 92-121`, `app_server/middlewares/authMiddleware.ts:56-65`, `app_server/services/sessionService.ts:60-70`
- Category: Security / Anti-Fraud / Business Logic
- What's wrong: The bot maintains user ban status via `is_banned: True` on user documents in Firestore (enforced by `BanCheckMiddleware` in the Telegram bot). However, `app_server`'s authentication endpoints (`verifyVaultId`, `verifyIntegrity`) and session guard middleware (`authenticateSession` / `validateSession`) NEVER inspect `userData.is_banned`.
- Why it matters: A fraudulent or abusive user banned by administrators in Telegram can continue to use the Android app unimpeded. They can verify their Vault ID, pass integrity checks, receive a session token, access protected routes (`/telemetry/log-session`, `/auth/me`), and sync device data. Furthermore, when an admin bans a user, `current_session_token` is not invalidated.
- Fix direction: In `verifyVaultId`, `verifyIntegrity`, and `validateSession`, inspect `userData.is_banned`. If `is_banned === true`, immediately reject with 403 Forbidden ("Account is suspended"). In the Telegram admin ban handler, delete/clear `current_session_token` on the banned user document.

### [HIGH] Missing Direct Dependency psutil in pyproject.toml Crashes Admin Bot Status
- File: `pyproject.toml` & `src/instavault/handlers/admin/bot_status.py`
- Line(s): `pyproject.toml:16-35`, `src/instavault/handlers/admin/bot_status.py:17`
- Category: Dependency / Configuration
- What's wrong: `pyproject.toml` specifies runtime dependencies for `aiogram`, `firebase-admin`, `redis`, `aiohttp`, etc., but completely omits `psutil`. However, `handlers/admin/bot_status.py` executes `import psutil` at line 17 and relies on it for CPU, memory, and disk telemetry.
- Why it matters: In any clean deployment or standard installation via `pip install .` or `pip install -e .` (as specified in `Makefile`), `psutil` will not be installed. When an administrator navigates to the Bot Status screen in the admin dashboard, the handler crashes immediately with `ModuleNotFoundError: No module named 'psutil'`.
- Fix direction: Add `"psutil>=5.9.0"` to the `dependencies` list in `pyproject.toml`.

### [HIGH] Express App Missing trust proxy Setting Causes Rate Limiter to Throttle All Users Globally or Crash
- File: `app_server/server.ts` & `app_server/middlewares/rateLimiter.ts`
- Line(s): `app_server/server.ts:11-16`, `app_server/middlewares/rateLimiter.ts:16-26, 34-44`
- Category: Infrastructure / Networking / Rate Limiting
- What's wrong: `app_server` applies `express-rate-limit` (v8.6.0) to `/auth/*` (10 req / 15 min) and `/telemetry/*` (100 req / 15 min). However, `app.set("trust proxy", 1)` is never configured on the Express instance in `server.ts`.
- Why it matters: When deployed behind any reverse proxy, ingress, load balancer, or CDN (Cloudflare, Nginx, Render, AWS ALB, GCP Cloud Run), `req.ip` resolves to the reverse proxy's IP address instead of the client's public IP. As a result, all mobile app users worldwide share a single combined rate limit bucket of 10 requests per 15 minutes. Once 10 requests occur across all users, every subsequent user is blocked with HTTP 429 "Too many requests". Moreover, `express-rate-limit` v8 defaults to throwing a fatal validation error when it detects `X-Forwarded-For` without `trust proxy`.
- Fix direction: Configure `app.set("trust proxy", 1)` in `app_server/server.ts` before mounting rate limiters.

### [HIGH] Development Mode Integrity Bypass Always Fails on Nonce Consumption
- File: `app_server/services/integrityService.ts` & `app_server/controllers/authController.ts`
- Line(s): `app_server/services/integrityService.ts:45-63`, `app_server/controllers/authController.ts:101-110`
- Category: Logic / Developer Experience / Testing
- What's wrong: To support testing without a physical Android device, `integrityService.ts` implements a dev mode bypass (`if (config.nodeEnv === "development")`) that returns a mock verdict with `nonce: "dev-mock-nonce"`. However, in `authController.ts`, line 104 immediately executes `await consumeNonce(integrityVerdict.requestDetails?.nonce, normalizedId)` which searches Firestore's `active_nonces` collection for `"dev-mock-nonce"`.
- Why it matters: The real nonce generated during Step 1 (`verifyVaultId`) is a dynamic 32-byte cryptographically random string (e.g. `dGVzdF9ub25jZQ...`), not `"dev-mock-nonce"`. Since `"dev-mock-nonce"` does not exist in Firestore, `consumeNonce` throws `NonceValidationError("Nonce is missing, expired, or was already used.")`, causing `authController` to return 401 Unauthorized. The entire development mode bypass is completely broken and cannot be used for local testing.
- Fix direction: In development mode, either bypass `consumeNonce` when `config.nodeEnv === "development"`, or have `verifyPlayIntegrity` accept and echo back the client-supplied/stored nonce.

### [HIGH] Hardcoded Default Credentials Fallback in GoogleAuth Fails Outside GCP
- File: `app_server/services/integrityService.ts` & `app_server/config/firebase.ts`
- Line(s): `app_server/services/integrityService.ts:70-76`, `app_server/config/firebase.ts:8-17`
- Category: Authentication / Cloud Configuration
- What's wrong: In `firebase.ts`, the app initializes Firebase Admin by directly reading `firebase_credentials.json` via `cert(serviceAccount)`. However, in `integrityService.ts`, it instantiates `new GoogleAuth({ scopes: ["https://www.googleapis.com/auth/playintegrity"] })` with no `keyFile` argument and without setting `process.env.GOOGLE_APPLICATION_CREDENTIALS`.
- Why it matters: `GoogleAuth` does NOT inherit credentials from Firebase Admin. When running on standard servers (VPS, Docker, Render, DigitalOcean, local machines) where Google Application Default Credentials (ADC) are not set in the environment, `auth.getClient()` throws a fatal error: `Could not load the default credentials`. Production integrity checks crash with 500 Internal Server Error.
- Fix direction: Pass `keyFilename: config.firebaseCredentialsPath` into `new GoogleAuth({ keyFilename: config.firebaseCredentialsPath, scopes: ... })` or set `process.env.GOOGLE_APPLICATION_CREDENTIALS = serviceAccountPath` on startup in `firebase.ts`.

### [MEDIUM] Worker Leaderboard Exposes Insecure Dev Secret Fallback Allowing Unauthenticated Triggers
- File: `worker-leaderboard/src/index.js`
- Line(s): 21-24
- Category: Security / Access Control
- What's wrong: In the Cloudflare Worker `fetch` handler, the secret authorization check falls back to a hardcoded string: `if (url.searchParams.get("secret") !== (env.SYNC_SECRET || "dev-secret-123"))`.
- Why it matters: If a deployment does not configure `SYNC_SECRET` in Cloudflare Worker environment variables, the worker falls back to `"dev-secret-123"`. Anyone on the public internet can trigger `GET /?secret=dev-secret-123` in an automated loop, spamming the Firestore REST API and Upstash Redis, exhausting daily free-tier quotas or causing billing spikes.
- Fix direction: Do not fall back to a hardcoded dev secret in production; require `env.SYNC_SECRET` to be non-empty, and return 500/401 if not configured.

### [MEDIUM] Trailing Slash in Upstash REST URL Malforms Redis Endpoint and Fails Worker Sync
- File: `worker-leaderboard/src/index.js`
- Line(s): 120-128
- Category: Integration / URL Formatting
- What's wrong: Line 120 constructs the Redis endpoint via string interpolation without sanitizing trailing slashes: `const redisUrl = `${UPSTASH_REDIS_REST_URL}/set/leaderboard:lifetime?EX=900`;`.
- Why it matters: A very common configuration practice (and Upstash console copy-paste) provides the REST URL with a trailing slash (e.g., `https://...upstash.io/`). This produces `https://...upstash.io//set/leaderboard:lifetime?EX=900`. The double slash `//` causes Upstash's HTTP routing to fail or return 404/redirect, causing the 10-minute cron job to fail silently or log `Redis sync failed (404)`.
- Fix direction: Sanitize the URL before appending the path: `const baseUrl = UPSTASH_REDIS_REST_URL.replace(/\/+$/, "");`.

### [MEDIUM] Unbounded Session Lifetime with No Expiry or Invalidation
- File: `app_server/services/sessionService.ts` & `app_server/middlewares/authMiddleware.ts`
- Line(s): `app_server/services/sessionService.ts:39-45, 60-70`
- Category: Security / Session Management
- What's wrong: `createSession` stores `current_session_token` and `last_app_login` on the user document, but does not record an expiration timestamp (`session_expires_at`). Furthermore, `validateSession` performs no expiration or freshness checks.
- Why it matters: Once issued, an app session token remains valid indefinitely. If a user's mobile device is decommissioned, lost, compromised, or a token is intercepted, there is no token expiration mechanism or explicit logout endpoint (`/auth/logout`) to revoke it.
- Fix direction: Introduce a `session_expires_at` timestamp (e.g. 30 days) and check `if (userData.session_expires_at < Date.now()) return false;`, and provide a `/auth/logout` endpoint that clears `current_session_token`.

### [LOW] Plaintext Request Body Logging Leaks Sensitive Tokens and Identifiers
- File: `app_server/server.ts`
- Line(s): 19-23
- Category: Information Exposure / Logging
- What's wrong: The global request logging middleware in `server.ts` outputs `console.log(`[BODY] ${JSON.stringify(req.body)}`);` on every request.
- Why it matters: Client integrity tokens, nonces, device telemetry, and hardware fingerprints are logged in plaintext to stdout, exposing them to log ingestion pipelines, cloud log aggregators, and unauthorized console viewers.
- Fix direction: Sanitize or redact sensitive fields (`integrity_token`, passwords, session tokens) before logging `req.body`, or disable body logging in production.

### [LOW] Linux-Specific fuser Command and Port Discrepancy in Makefile
- File: `Makefile`
- Line(s): 10
- Category: Portability / Tooling
- What's wrong: `make run` executes `@fuser -k 8099/tcp 2>/dev/null || true`. `fuser` is a Linux-specific utility (from `psmisc`) that is absent on macOS and minimal Docker images (Alpine/Debian-slim). Furthermore, it targets port 8099, whereas `main.py` defaults to `WEBHOOK_PORT = 8080`.
- Why it matters: Developers on macOS or minimal Linux containers will encounter errors or silent failures when running `make run`, and any stuck process on the default port 8080 is not terminated.
- Fix direction: Use a portable Python one-liner or shell check, or parameterize the port based on `$(WEBHOOK_PORT)`.

### [NEEDS-CONFIRMATION] Orphaned Nonce Accumulation in Firestore active_nonces Collection
- File: `app_server/services/nonceService.ts`
- Line(s): 15-24, 33-66
- Category: Database Maintenance / Cost & Resource Leak
- What's wrong: `storeNonce` creates documents in the `active_nonces` collection with `expires_at: Timestamp.fromMillis(Date.now() + NONCE_TTL_MS)`. However, `consumeNonce` only deletes a nonce when a verification attempt is actually made for that specific nonce. If an app client requests a nonce via `/auth/verify-vault-id` but never submits `/auth/verify-integrity` (abandoned login, network failure, bot abuse), the nonce document is never deleted by the application code.
- Why it matters: Unless a Google Cloud Firestore TTL Policy is explicitly configured on the `active_nonces` collection targeting the `expires_at` field, these orphaned documents will accumulate in Firestore forever, increasing storage usage and query overhead. Needs confirmation on whether a GCP TTL policy is active or whether a background cleanup job/cron is required.
- Fix direction: Confirm if GCP Firestore TTL policy is enabled on `active_nonces.expires_at`; if not, add a TTL policy in Cloud Console or implement a periodic cleanup routine.
