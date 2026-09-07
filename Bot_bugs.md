# Comprehensive Codebase Security & Architecture Audit

This report strictly focuses on realistic vulnerabilities, edge cases, state leaks, and crash risks for a Telegram Bot architecture (Linux VPS/Render Worker) serving ~5,000 DAU. 

## 🔴 CRITICAL CRASH & DATA LOSS

### 1. Firestore Datetime vs Redis String Desync
* **File:** `src/instavault/database/db_manager.py` (Line ~105-121)
* **Explanation:** When fetching a user directly from Firestore, dates like `created_at` are returned as native Python `datetime` objects. However, when cached in Upstash Redis, the custom encoder serializes them into ISO strings. When a cache hit occurs, `json.loads` returns a string.
* **Impact:** Any downstream handler attempting to call `.strftime()` on the date will immediately crash with an `AttributeError`. At 5,000 DAU, high cache hit rates will consistently trigger this crash.

### 2. Permanent Link Lockout (State Leak)
* **File:** `src/instavault/database/db_manager.py` (Line ~628-685)
* **Explanation:** The bot creates a link lock document in `ACTIVE_LINK_LOCKS_COL` to prevent concurrent orders for the exact same Instagram URL. However, `delete_link_lock()` is *only* ever called when an order is cancelled/refunded.
* **Impact:** If an order succeeds and is successfully delivered via the SMM API, the lock is never removed. The user (and all other users) will be permanently blocked from ever purchasing views for that specific URL again.

### 3. Graceful Shutdown / In-Flight Write Severance
* **File:** `src/instavault/__main__.py` (Lines ~224-262) & `app_server/server.ts`
* **Explanation:** Neither the Python Bot nor the Express Server handles `SIGTERM` (the default signal sent by Render/Systemd for a redeploy or scale down). The shutdown hook closes connections but doesn't wait for pending `asyncio` tasks.
* **Impact:** Any in-flight Firestore transactions, active API callbacks, or background Redis syncs running during a routine VPS reboot or Render redeploy will be violently severed, resulting in corrupted states, abandoned locks, and lost ledger data.

### 4. Broadcast Progress Background Task Crash
* **File:** `src/instavault/admin_panel/broadcast.py` (Line ~642)
* **Explanation:** During a broadcast loop, individual messages are protected by a `try/except`. But the final `ticket_msg.edit_text(summary_text)` happens entirely unprotected outside the loop.
* **Impact:** If an admin deletes the live "Progress" message mid-broadcast, this final call throws a `TelegramBadRequest`, crashing the background worker *before* cleanup logic fires.

### 5. Blind Reference Update on Missing Referrer (Onboarding Blocker)
* **File:** `src/instavault/database/db_manager.py` (Line ~293)
* **Explanation:** During `_create_user_tx`, the code calls `tx.update(referrer_ref, ...)` without verifying the referrer document still exists.
* **Impact:** If a new user clicks a referral link for a deleted or purged account, Firestore will throw a `NotFound` exception. The transaction will fail, permanently blocking that user from completing onboarding.

---

## 🟠 LOGICAL LOOPHOLE & RACE CONDITIONS

### 6. Double Refund Race Condition (Economy Inflation)
* **File:** `src/instavault/database/db_manager.py` (Line ~748-772)
* **Explanation:** `cancel_order_and_refund` uses a Time-Of-Check to Time-Of-Use (TOCTOU) pattern without wrapping it in a Firestore Transaction. It reads `pending_approval`, then updates the status and refunds.
* **Impact:** If two admins concurrently cancel the same order, both requests will pass the read check and sequentially refund the user twice, artificially inflating the Spark economy.

### 7. Shortlink Task Duplicate Reward
* **File:** `src/instavault/handlers/tasks_shortener.py` & `db_manager.py` (Line ~1144)
* **Explanation:** Checking `last_shortener_task_date` occurs outside an atomic transaction.
* **Impact:** A malicious user can write a script to rapidly trigger the shortlink deep-link callback 20 times concurrently. All 20 read the un-updated date and trigger `complete_shortener_task`, granting 20x daily rewards.

### 8. Negative Balances via Admin Deduct
* **File:** `src/instavault/admin_panel/user_control.py` (Line ~927-945)
* **Explanation:** The admin panel performs a local balance check (`current < amount`) before issuing a non-transactional `deduct_spark_balance`.
* **Impact:** If a user places an order at the exact millisecond an admin deducts their sparks, the balance is legitimately driven into the negatives in Firestore.

### 9. Media Penalty Misclassification
* **File:** `src/instavault/handlers/orders.py` (Line ~153)
* **Explanation:** When the bot expects an Instagram link, it reads `message.text`. If a user confusingly sends a photo or sticker, `message.text` evaluates to `None`, which the handler coerces to `""`.
* **Impact:** The empty string fails regex, registering as a malicious/invalid URL attempt. This increments the Redis penalty counter, resulting in a 30-second ban for simply sending an image.

### 10. Swallowed Cache Invalidations
* **File:** `src/instavault/database/redis_manager.py` (Line ~128-152)
* **Explanation:** `invalidate_user_cache` implements a 3-retry loop. If it fails (e.g., Upstash timeout), it swallows the error gracefully and returns.
* **Impact:** The application continues running, but the user views fundamentally desynchronized data (e.g., pre-spend spark balances) for up to 24 hours.

### 11. Structurally Broken Onboarding State (Middleware Collision)
* **File:** `src/instavault/middlewares/fsm_reset.py` (Line ~44) & `start.py`
* **Explanation:** `fsm_reset.py` blindly calls `await state.clear()` on any callback starting with `ob_`.
* **Impact:** The `OnboardingState` set during `/start` is instantly destroyed upon clicking the first button. The FSM implementation in `start.py` is entirely non-functional (though currently masked by fallback data fetching).

---

## 🟡 MINOR UX & PERFORMANCE

### 12. Unhandled `TelegramBadRequest` Error Spam
* **File:** `src/instavault/admin_panel/dashboard.py` & `user_control.py`
* **Explanation:** Widespread lack of catching `message is not modified` when editing inline keyboards.
* **Impact:** Users double-tapping buttons get the UI loading circle stuck permanently (because `query.answer()` fails to execute) and it pollutes the VPS logs heavily.

### 13. O(N) Pagination Scaling Issue
* **File:** `src/instavault/database/db_manager.py` (Line ~527-534)
* **Explanation:** Relies on Firestore `.offset()` for order history pagination.
* **Impact:** At 5,000 DAU, power users will generate large order histories. `.offset()` bills for every skipped document and incurs O(N) read latency.

### 14. Referral UX Notification Discrepancy
* **File:** `src/instavault/handlers/start.py`
* **Explanation:** The backend awards referred users `WELCOME_BONUS` + `REFEREE_BONUS`. The frontend UI strictly notifies them they only received the `WELCOME_BONUS`.
* **Impact:** Minor confusion; users get more sparks than they were explicitly promised.
