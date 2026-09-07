# Comprehensive Bug Report 2026

This artifact synthesizes the findings from 15 peer-review security and QA audits of the `Insta_vault_bot` codebase. 
All bugs are categorized strictly by severity into CRITICAL (Showstoppers), MEDIUM (Logic Flaws), and LOW (Minor/Typos).

## 🔴 CRITICAL (Showstoppers)

### 1. Missing Application Integrity Verification
* **File:** `app_server/services/integrityService.ts`
* **Line(s):** 95-107
* **Explanation:** The `verifyPlayIntegrity` function completely fails to validate the `verdict.appIntegrity?.appRecognitionVerdict`. It accepts requests from tampered/repackaged apps.
* **Theoretical Solution:** Throw an error if the verdict is not `"PLAY_RECOGNIZED"`.

### 2. Invalid Upstash Redis REST API Syntax (EX)
* **File:** `worker-leaderboard/src/index.js`
* **Line(s):** 120-129
* **Explanation:** Upstash REST API does not support `?EX=900` query parameters for expiration. It causes the leaderboard key to never expire or crashes.
* **Theoretical Solution:** Pass the entire command `["SET", "key", "val", "EX", 900]` in the JSON body.

### 3. Leaderboard Exploit via Order Refunds
* **File:** `src/instavault/database/db_manager.py`
* **Line(s):** 772-773
* **Explanation:** Cancelling orders refunds sparks into both `spark_balance` and `lifetime_sparks`. Users can place/cancel orders infinitely to inflate their leaderboard rank.
* **Theoretical Solution:** Add a dedicated refund function that updates `spark_balance` without touching `lifetime_sparks`.

### 4. Race Condition in Order Cancellation (Double-Refund)
* **File:** `src/instavault/database/db_manager.py`
* **Line(s):** 728-794
* **Explanation:** `cancel_order_and_refund` spans multiple independent DB queries without a transaction. Concurrent cancellation requests can result in a double-refund.
* **Theoretical Solution:** Wrap the cancellation/refund logic inside an `@async_transactional` block.

### 5. Unreferenced Async Background Task (Garbage Collection Risk)
* **File:** `src/instavault/admin_panel/broadcast.py`
* **Line(s):** 330-340
* **Explanation:** Scheduled broadcast tasks are launched via `asyncio.create_task` with no strong references. The Python GC might destroy them mid-execution.
* **Theoretical Solution:** Store a reference to the task in a global `set` until completion.

### 6. Client-Side Trust / API Spoofing in Trivia Quiz
* **File:** `src/instavault/handlers/games_dummy.py`
* **Line(s):** 308-312, 334
* **Explanation:** Trivia answers are stored in `callback_data`. Malicious clients can spam correct callback data to farm infinite points.
* **Theoretical Solution:** Store correct answers in the server-side state (`F2P_DB`) and validate user input against it.

### 7. FSM State Leak on Order Cancellation
* **File:** `src/instavault/handlers/orders.py`
* **Line(s):** 336-347
* **Explanation:** The cancel handler `cb_cancel_order` does not receive the `FSMContext` and never clears the state, permanently trapping the user in `waiting_for_link`.
* **Theoretical Solution:** Add `state: FSMContext` to the signature and call `await state.clear()`.

### 8. State Remains Active During Order Confirmation
* **File:** `src/instavault/handlers/orders.py`
* **Line(s):** 214-226
* **Explanation:** Upon linking successfully, state is left active as `waiting_for_link`. Users can accidentally overwrite their link or get trapped.
* **Theoretical Solution:** Clear state instantly upon a valid link or change to a unique `waiting_for_confirmation` state.

### 9. Rate Limiting Bypass for Commands
* **File:** `src/instavault/middlewares/throttling.py`
* **Line(s):** 68-74
* **Explanation:** The throttling logic explicitly skips any text starting with `/` (unless `/start`). All other commands bypass rate-limiting entirely.
* **Theoretical Solution:** Route other slash commands through the micro-throttling pipeline.

### 10. Security/Data Leak in Request Logger
* **File:** `app_server/server.ts`
* **Line(s):** 21
* **Explanation:** The global logger outputs the raw request body containing sensitive auth tokens/nonces to standard output in plaintext.
* **Theoretical Solution:** Implement payload redaction or disable request body logging in production.

### 11. Invalid Package Versions Blocking Installation
* **File:** `app_server/package.json`
* **Line(s):** 22, 32
* **Explanation:** Depends on non-existent `typescript: ^7.0.2` and `uuid: ^14.0.1`, which crashes `npm install`.
* **Theoretical Solution:** Fix versions to real releases (e.g., TS 5.x, UUID 10.x).

### 12. Hardcoded Secrets Exposed in Environment File
* **File:** `.env`
* **Line(s):** 4, 14, 18, 19, 22, 25, 30
* **Explanation:** Committing actual API keys and tokens in `.env` is a major security flaw.
* **Theoretical Solution:** Strip secrets, rename to `.env.example`, and `.gitignore` the real `.env`.

### 13. Telegram API callback_data Length Limit Exceeded
* **File:** `src/instavault/keyboards/inline.py`
* **Line(s):** 334
* **Explanation:** The callback `order_confirm:{package_type}:{nonce}` will exceed Telegram's strict 64-byte limit if nonce is a UUID, crashing the menu.
* **Theoretical Solution:** Store data in Redis via a short key and pass only the short key in `callback_data`.

### 14. Inconsistent Casing Logic in Vault ID Normalization
* **File:** `app_server/controllers/authController.ts` & `app_server/middlewares/authMiddleware.ts`
* **Line(s):** 27-29, 85-87, 51-53
* **Explanation:** "vlt-abcd" yields "VLT-ABCD", while "abcd" yields "VLT-abcd". This strict mismatch causes 404 Database lookup failures for valid users.
* **Theoretical Solution:** Normalize string inputs strictly (e.g. `trim().toUpperCase()`) before prefixing.

---

## 🟡 MEDIUM (Logic Flaws)

### 1. Potential Authentication Bypass via Undefined Token Matching
* **File:** `app_server/services/sessionService.ts`
* **Line(s):** 69
* **Explanation:** `undefined === undefined` returns true if a user without a session token hits the endpoint with a missing auth header.
* **Theoretical Solution:** Ensure `sessionToken` is truthy before comparing.

### 2. Silent failure on negative Admin IDs
* **File:** `src/instavault/core/config.py`
* **Line(s):** 45-47
* **Explanation:** `.isdigit()` rejects negative channel IDs, silently removing them from `ADMIN_IDS`.
* **Theoretical Solution:** Parse with `try...except ValueError` instead of `.isdigit()`.

### 3. Transaction Abort on Invalid/Deleted Referrer
* **File:** `src/instavault/database/db_manager.py`
* **Line(s):** 291-300
* **Explanation:** Using `.update()` on a non-existent referrer throws `NotFound`, aborting new user signups.
* **Theoretical Solution:** Fetch the document or use `.set(..., merge=True)`.

### 4. Race Condition in complete_shortener_task
* **File:** `src/instavault/database/db_manager.py`
* **Line(s):** 1144-1181
* **Explanation:** Uses blind `Increment` instead of a transactional validation check on the date, permitting double-reward races.
* **Theoretical Solution:** Convert to `@async_transactional` to safely check the `last_shortener_task_date`.

### 5. Leaderboard Cache Key Ignores limit Parameter
* **File:** `src/instavault/database/db_manager.py`
* **Line(s):** 423-437
* **Explanation:** `get_leaderboard(limit=10)` caches as `leaderboard:lifetime`. Future calls asking for 50 limits receive the cached 10.
* **Theoretical Solution:** Add the limit directly to the Redis cache key.

### 6. Fractional Reward Loss in Idle Tycoon
* **File:** `src/instavault/handlers/games_dummy.py`
* **Line(s):** 235, 268-274
* **Explanation:** Calculating fractional rewards via `int()` and strictly resetting the timer to `time.time()` permanently deletes uncollected fractions.
* **Theoretical Solution:** Increment the timer only by the exact duration of the consumed sparks.

### 7. Unhandled Missing Referral Code
* **File:** `src/instavault/handlers/referrals.py`
* **Line(s):** 36, 39, 51
* **Explanation:** If a user lacks a code, it uses `"—"`, generating broken deep links.
* **Theoretical Solution:** Handle missing codes properly by generating one.

### 8. Repeated User Notifications on Status Check
* **File:** `src/instavault/handlers/admin.py`
* **Line(s):** 360-384
* **Explanation:** Admins checking already-refunded orders trigger duplicate spam DM notifications to users.
* **Theoretical Solution:** Exit early if `ValueError` triggers.

### 9. Loss of HTML Formatting on Message Edits
* **File:** `src/instavault/handlers/admin.py`
* **Line(s):** 141, 222, 237, 337, 366
* **Explanation:** `query.message.text` strips HTML tags. Re-editing destroys all ticket bolding/monospace fonts.
* **Theoretical Solution:** Use `query.message.html_text`.

### 10. Missing Link Lock Release on Cancellation
* **File:** `src/instavault/handlers/admin.py`
* **Line(s):** 128-136
* **Explanation:** Cancelled orders fail to release the active link lock, permanently blocking the user from placing that link again.
* **Theoretical Solution:** Call `delete_link_lock(ig_url)` inside the cancel callback.

### 11. Hardcoded Fallback Bot Username in Deep Links
* **File:** `src/instavault/handlers/tasks_shortener.py`
* **Line(s):** 108, 113, 129
* **Explanation:** Falls back to `"InstaVaultBot"` if config is missing, routing user completions to the wrong bot entirely.
* **Theoretical Solution:** Dynamically fetch `bot_info.username` at runtime.

### 12. Dead/Unreachable Code for `/cancel` Command
* **File:** `src/instavault/handlers/main_menu.py`
* **Line(s):** 748-755
* **Explanation:** The general message handler unconditionally intercepts all `/cancel` calls before the specific cancellation handler can run.
* **Theoretical Solution:** Reorder handlers so `/cancel` is evaluated first.

### 13. Missing Keyboard Update leads to Spam Vulnerability
* **File:** `src/instavault/handlers/main_menu.py`
* **Line(s):** 641-674
* **Explanation:** Sending large APKs via `answer_document` without removing the inline button allows users to spam requests and trigger `FloodWait`.
* **Theoretical Solution:** Remove `reply_markup` from the message instantly.

### 14. Unhandled `sl_` Deep Links for New Users
* **File:** `src/instavault/handlers/start.py`
* **Line(s):** 102-108
* **Explanation:** New users using `sl_` shortener links have their context thrown away during onboarding.
* **Theoretical Solution:** Extract the argument and handle shortener reward upon finishing onboarding.

### 15. Suboptimal Navigation Behavior (Message Spam)
* **File:** `src/instavault/handlers/start.py`
* **Line(s):** 289-300
* **Explanation:** `cb_nav_dashboard` uses `edit=False`, creating an orphaned message with a dead keyboard rather than editing in place.
* **Theoretical Solution:** Call with `edit=True`.

### 16. Unanswered Throttled Callback Queries Cause UI Hang
* **File:** `src/instavault/middlewares/throttling.py`
* **Line(s):** 97
* **Explanation:** Dropped callbacks don't answer Telegram, leaving a spinning loading wheel on the user's screen until timeout.
* **Theoretical Solution:** Issue `await event.answer()` when dropping it.

### 17. Missing Strong Reference to Background Tasks
* **File:** `src/instavault/middlewares/ban_check.py`
* **Line(s):** 86
* **Explanation:** Task references for `record_user_activity` are dropped, making them vulnerable to garbage collection.
* **Theoretical Solution:** Store strongly typed references in a set.

### 18. Repeated Banned User Clicks Throw `MessageNotModified`
* **File:** `src/instavault/middlewares/ban_check.py`
* **Line(s):** 79-80
* **Explanation:** Banned users clicking buttons repeatedly crash the middleware by attempting to edit the message to identical text.
* **Theoretical Solution:** Catch and suppress `TelegramBadRequest`.

### 19. Missing "Coming Soon" Callback Registration
* **File:** `src/instavault/admin_panel/user_control.py`
* **Line(s):** 126-129, 306-308
* **Explanation:** `uc_transactions` is missing from the `_COMING_SOON_UC` set, causing dead clicks and warning logs.
* **Theoretical Solution:** Add the callback name to the set.

### 20. Missing Integer Type Cast for `chat_id`
* **File:** `src/instavault/admin_panel/broadcast.py`
* **Line(s):** 389-390
* **Explanation:** Scheduled broadcasts fail to cast `target_uid` to integer for `chat_id`.
* **Theoretical Solution:** Add the missing `int()` wrapper.

### 21. Potential Type Error for Web Server Port
* **File:** `src/instavault/__main__.py`
* **Line(s):** 217, 318
* **Explanation:** `WEBAPP_PORT` string is passed directly into aiohttp, resulting in a `TypeError`.
* **Theoretical Solution:** Explicitly cast it to `int()`.

### 22. Unhandled Non-200 HTTP Responses
* **File:** `src/instavault/services/smm_api.py`
* **Line(s):** 66-72
* **Explanation:** Lack of `resp.status` validation crashes JSON decoding if the SMM Panel returns HTML errors.
* **Theoretical Solution:** Check HTTP status and raise an error explicitly.

### 23. Invalid Package Versions (pyproject.toml)
* **File:** `pyproject.toml`
* **Line(s):** 25, 31
* **Explanation:** Points to `redis==8.0.0` and `pydantic-settings==2.14.2` which do not exist on PyPI.
* **Theoretical Solution:** Validate and downgrade to correct latest stable versions.

### 24. Unhandled Synchronous Exceptions on Startup
* **File:** `app_server/config/firebase.ts`
* **Line(s):** 13
* **Explanation:** Lack of try-catch on `fs.readFileSync` completely crashes the server if the JSON is malformed.
* **Theoretical Solution:** Wrap in `try/catch`.

### 25. Potential NaN Port Assignment
* **File:** `app_server/config/environment.ts`
* **Line(s):** 9
* **Explanation:** Unvalidated `parseInt()` falls back to `NaN`, breaking the express `listen` port.
* **Theoretical Solution:** Provide a strict numeric fallback check `isNaN()`.

### 26. Ambiguous Naive Datetime Localization
* **File:** `src/instavault/utils/helpers.py`
* **Line(s):** 41-43
* **Explanation:** Directly converting naive datetimes as IST misrepresents naive UTC timestamps.
* **Theoretical Solution:** Default naive datetimes to UTC before localizing.

### 27. Blocking Database Operations Contradicting Fire-and-Forget
* **File:** `app_server/controllers/telemetryController.ts`
* **Line(s):** 87-108
* **Explanation:** The endpoint uses `await Promise.all()` before issuing `202 Accepted`, blocking the client.
* **Theoretical Solution:** Remove `await` and let the promise execute in the background.

### 28. Missing Whitespace Sanitization (Trim)
* **File:** `app_server/controllers/authController.ts` & `app_server/middlewares/authMiddleware.ts`
* **Line(s):** 21, 75, 51
* **Explanation:** `vault_id` isn't trimmed, so accidental spaces lead to broken prefixes like `"VLT- 1234"`.
* **Theoretical Solution:** `.trim()` all ID inputs.

### 29. Rate Limiter IP Blocking Risk Behind Proxies
* **File:** `app_server/middlewares/rateLimiter.ts`
* **Line(s):** 16-26
* **Explanation:** Without `trust proxy`, reverse proxies share a single IP limit and globally ban all clients.
* **Theoretical Solution:** Explicitly enable `app.set('trust proxy', 1)`.

---

## 🟢 LOW (Minor/Typos)

### 1. Nonce Not Consumed on Vault ID Mismatch
* **File:** `app_server/services/nonceService.ts`
* **Line(s):** 55-57
* **Explanation:** Throwing an error aborts the transaction without deleting the invalid nonce.
* **Theoretical Solution:** Delete the nonce explicitly before throwing the error.

### 2. Copy-paste leftover string literal
* **File:** `src/instavault/constants/rewards.py`
* **Line(s):** 33-38
* **Explanation:** Extraneous pseudo-docstring leftover in the middle of code.
* **Theoretical Solution:** Remove or relocate.

### 3. Brittle path resolution
* **File:** `src/instavault/core/config.py`
* **Line(s):** 67-69
* **Explanation:** Messy nested `os.path.dirname` declarations.
* **Theoretical Solution:** Use `pathlib`.

### 4. Unreferenced Async Task
* **File:** `src/instavault/database/db_manager.py`
* **Line(s):** 366
* **Explanation:** No reference saved for `record_new_account`.
* **Theoretical Solution:** Keep a strong set reference.

### 5. Suspicious Indexing on Firestore Aggregation Result
* **File:** `src/instavault/database/db_manager.py`
* **Line(s):** 958, 1019, 1104-1105, 1114-1115
* **Explanation:** Uses `result[0][0].value`, which raises `TypeError`.
* **Theoretical Solution:** Safely access via `result[0].value`.

### 6. Potential State Loss on Network Error
* **File:** `src/instavault/handlers/games_dummy.py`
* **Line(s):** 122-126
* **Explanation:** Ticket deducted before API network call succeeds.
* **Theoretical Solution:** Execute DB write only after the Telegram API succeeds.

### 7. Race Condition in User Data Initialization
* **File:** `src/instavault/handlers/games_dummy.py`
* **Line(s):** 27-35
* **Explanation:** `if user_id not in F2P_DB:` introduces initialization races.
* **Theoretical Solution:** Use `F2P_DB.setdefault`.

### 8. Misplaced Docstrings (Various)
* **File:** `admin.py`, `tasks_shortener.py`, `main_menu.py`, `start.py`
* **Line(s):** Admin (118, 173, 270), Tasks (78-81), MainMenu (162-167), Start (325-331)
* **Explanation:** Floating string literals following `if` statements instead of immediately after `def`.
* **Theoretical Solution:** Move strings to the top line of the method.

### 9. Fragile Message Trimming via String Splits
* **File:** `src/instavault/handlers/admin.py`
* **Line(s):** 337, 366
* **Explanation:** Hardcoded string splitting logic (`\n\n✅`) to parse message text is fragile.
* **Theoretical Solution:** Regenerate template from state variables.

### 10. Brittle Instagram Handle Parsing Logic
* **File:** `src/instavault/handlers/main_menu.py`
* **Line(s):** 89-93
* **Explanation:** Blind sequential regex substitution can incorrectly parse non-standard URLs into false usernames (e.g., `"p"`).
* **Theoretical Solution:** Use `urllib.parse` strictly.

### 11. Potential UnboundLocalError from Silent Failure
* **File:** `src/instavault/handlers/orders.py`
* **Line(s):** 163-173, 180-182
* **Explanation:** Swallows exceptions around `redis`, leading to unbound references later on.
* **Theoretical Solution:** Define defaults safely before `try` blocks.

### 12. Potential ValueError Crash
* **File:** `src/instavault/admin_panel/bot_status.py`
* **Line(s):** 129
* **Explanation:** Blind integer cast on cache elements crashes the page if a bad value exists.
* **Theoretical Solution:** Handle safe validation prior to parsing.

### 13. Redundant `.replace()`
* **File:** `src/instavault/admin_panel/manage_user.py` & `user_control.py`
* **Line(s):** 128, 479
* **Explanation:** Overlapping replacements perform redundant operations.
* **Theoretical Solution:** Simplify to one `lstrip`.

### 14. Fragile URL Concatenation for Webhook
* **File:** `src/instavault/__main__.py`
* **Line(s):** 244
* **Explanation:** Potential for double slashes in Webhook URL paths.
* **Theoretical Solution:** Strip path segments correctly before joining.

### 15. Inline Imports within Function
* **File:** `src/instavault/__main__.py`
* **Line(s):** 132, 135
* **Explanation:** Handlers are imported inside a method body.
* **Theoretical Solution:** Hoist to module level.

### 16. Unoptimized HTTP Client Sessions
* **File:** `src/instavault/services/shortener_api.py`, `smm_api.py`
* **Line(s):** 53, 66
* **Explanation:** Reinitializes a new aiohttp session for every request instead of pooling.
* **Theoretical Solution:** Keep a shared, persistent `aiohttp.ClientSession`.

### 17. Potential TypeError with Firestore Data
* **File:** `src/instavault/services/transaction_history.py`
* **Line(s):** 148
* **Explanation:** Fails when amount is explicitly mapped to `None`.
* **Theoretical Solution:** Use logical OR (`tx.get("amount") or 0`).

### 18. Hardcoded Port
* **File:** `Makefile`
* **Line(s):** 10
* **Explanation:** Always kills `8099` instead of dynamic port.
* **Theoretical Solution:** Parse `.env` for variables.

### 19. Empty Environment Variable Assignment
* **File:** `.env`
* **Line(s):** 26
* **Explanation:** `APP_ENV=` may parse as empty strings, creating unexpected states.
* **Theoretical Solution:** Assign default values or remove.

### 20. Missing Global Error Handling and 404 Fallback
* **File:** `app_server/server.ts`
* **Line(s):** 43
* **Explanation:** Fallback errors produce HTML responses instead of standard JSON on API paths.
* **Theoretical Solution:** Add generic error and 404 middlewares.

### 21. Hardcoded Default GCP Project Number
* **File:** `app_server/config/environment.ts`
* **Line(s):** 11
* **Explanation:** Default number creates invisible risks of cross-project telemetry sending.
* **Theoretical Solution:** Mandate configuration with no defaults.

### 22. Fragile Rank Tier Calculation Logic
* **File:** `src/instavault/utils/helpers.py`
* **Line(s):** 82-86
* **Explanation:** Relies entirely on explicit dictionary insertion order for tier determination.
* **Theoretical Solution:** Sort dict items explicitly by value threshold.

### 23. Use of Logical OR instead of Nullish Coalescing
* **File:** `app_server/controllers/authController.ts`
* **Line(s):** 125-134
* **Explanation:** Discards legitimate `0` metrics.
* **Theoretical Solution:** Replace `||` with `??`.

### 24. Potential Information Disclosure via Error Messages
* **File:** `app_server/controllers/authController.ts`
* **Line(s):** 115
* **Explanation:** Dumps untrimmed upstream errors to the client API response body.
* **Theoretical Solution:** Return static sanitized strings.

### 25. Fragile Bearer Token Parsing
* **File:** `app_server/middlewares/authMiddleware.ts`
* **Line(s):** 48
* **Explanation:** `split(" ")[1]` breaks with extra whitespaces.
* **Theoretical Solution:** Implement regex parsing.
