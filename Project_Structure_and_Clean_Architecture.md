# Project Structure & Clean Architecture Report 🏗️

This artifact synthesizes the findings of 5 specialized Software Architecture agents focused strictly on file locations, naming conventions, structural integrity, and modularity.

## 🌳 Architectural Visualization

### ❌ Current "Before" Structure
The current structure suffers from "Monorepo Confusion", where Python build files at the root make it look like a single Python app. Furthermore, secrets and documentation pollute the root directory.

```text
/
├── .env
├── .gitignore
├── .pre-commit-config.yaml
├── Comprehensive_Bug_Report_2026.md        <-- Clutter
├── Deep_Dive_Bugs_Phase2.md                <-- Clutter
├── Performance_and_Refactoring_Audit.md    <-- Clutter
├── README.md
├── firebase_credentials.json               <-- Security risk in root
├── Makefile                                <-- Misplaced Python file
├── pyproject.toml                          <-- Misplaced Python file
├── __pycache__/                            <-- Junk artifact
├── tests/                                  <-- Misplaced Python tests
├── app_server/                             <-- Inconsistent naming (snake_case)
│   ├── controllers/
│   │   └── authController.ts               <-- Anti-pattern naming
│   └── ...
├── worker-leaderboard/                     <-- Inconsistent naming (kebab-case)
│   └── ...
└── src/
    └── instavault/
        ├── __main__.py                     <-- Contains UpdateLoggerMiddleware
        ├── admin_panel/
        │   ├── manage_user.py              <-- Ambiguous name
        │   └── user_control.py             <-- Ambiguous name
        ├── database/
        │   └── db_manager.py               <-- Contains inline exceptions
        ├── handlers/
        │   ├── games_dummy.py              <-- 'dummy' implies test code
        │   ├── tasks_shortener.py          <-- Cluttered tasks namespace
        │   └── main_menu.py                <-- FSM States mixed in
        └── ...
```

### ✅ Proposed "After" Structure
We recommend migrating to a standard `services/` (or `apps/`) monorepo layout. This guarantees proper isolation of dependencies, configurations, and tests.

```text
/
├── .env.example
├── .gitignore
├── .pre-commit-config.yaml
├── README.md
├── docs/                                   <-- New Home for Docs
│   ├── Comprehensive_Bug_Report_2026.md
│   ├── Deep_Dive_Bugs_Phase2.md
│   └── Performance_and_Refactoring_Audit.md
├── secrets/                                <-- New Home for Secrets (ignored)
│   └── firebase_credentials.json
├── services/                               <-- Monorepo Isolation
│   ├── api/  (was app_server)
│   │   ├── package.json
│   │   ├── controllers/
│   │   │   └── auth.controller.ts          <-- Standard TS dot-notation
│   │   ├── utils/
│   │   │   └── formatters.ts               <-- Extracted Vault ID normalizer
│   │   └── ...
│   │
│   ├── bot/  (was root Python files)
│   │   ├── Makefile
│   │   ├── pyproject.toml
│   │   ├── tests/
│   │   └── src/instavault/
│   │       ├── __main__.py                 <-- Middleware removed
│   │       ├── admin_panel/
│   │       │   ├── advanced_user_control.py<-- (was user_control.py)
│   │       │   ├── basic_user_actions.py   <-- (was manage_user.py)
│   │       │   └── keyboards.py            <-- Extracted inline UI keyboards
│   │       ├── core/
│   │       │   └── states.py               <-- Centralized FSM States
│   │       ├── database/
│   │       │   ├── exceptions.py           <-- Extracted business exceptions
│   │       │   ├── user_repository.py      <-- Split from db_manager
│   │       │   └── ...
│   │       ├── handlers/
│   │       │   ├── f2p_games.py            <-- (was games_dummy.py)
│   │       │   └── tasks/
│   │       │       └── shortener.py        <-- Clean tasks namespace
│   │       ├── middlewares/
│   │       │   ├── callback_guard.py       <-- Centralized validation guard
│   │       │   └── update_logger.py        <-- Extracted from __main__
│   │       ├── services/
│   │       │   └── exceptions.py           <-- Extracted API exceptions
│   │       └── utils/
│   │           ├── formatting.py           <-- View formatters
│   │           ├── http_client.py          <-- Shared aiohttp base class
│   │           └── permissions.py          <-- Centralized is_admin helper
│   │
│   └── leaderboard-worker/  (was worker-leaderboard)
│       └── ...
```

---

## 1. Git & Repo Cleanliness
* **Junk Files:** `__pycache__` at the root must be deleted. `firebase_credentials.json` must be moved into a `secrets/` directory to prevent accidental commits. Markdown audits should be moved into `docs/`.
* **The `.gitignore` Flaw:** `*.json` ignores *all* JSON files, critically omitting `package.json` in the Node server. Additionally, missing virtual environment (`.venv`) and testing (`.pytest_cache`) rules.
* **Commit Boundaries:** Changes to Python Bot (`services/bot`), Node Server (`services/api`), and Worker (`services/leaderboard-worker`) should be strictly committed separately using conventional scopes (e.g., `feat(bot):` vs `fix(api):`).

## 2. Naming Conventions Standardization
* **Root Directories:** Standardize on `kebab-case` for top-level directories (`api`, `leaderboard-worker`).
* **Node.js/TypeScript Files:** Transition from `camelCase.ts` to standard dot-notation `domain.role.ts` (e.g., `auth.controller.ts`, `auth.routes.ts`, `rate-limiter.middleware.ts`).
* **Python Bot Modules:**
  * Rename `manage_user.py` to `basic_user_actions.py` and `user_control.py` to `advanced_user_control.py` to disambiguate their purposes.
  * Rename `games_dummy.py` to `f2p_games.py`. "Dummy" implies testing mock-code, which it is not.
  * Move `tasks_shortener.py` into a dedicated `handlers/tasks/` subdirectory.

## 3. Modularity & Single Responsibility (SRP)
* **`__main__.py` Polluted with Classes:** The `UpdateLoggerMiddleware` is defined inside the entrypoint. It must be moved to `middlewares/update_logger.py`.
* **Exceptions Polluting Logic:** `DuplicateOrderError`, `SMMApiError`, etc., are defined inline next to connection logic. Move to `database/exceptions.py` and `services/exceptions.py`.
* **UI logic in Controllers/Services:** `admin.py`, `manage_user.py`, and `transaction_history.py` build their own `InlineKeyboardMarkup` objects dynamically. These must be moved to `keyboards/inline.py` or `admin_panel/keyboards.py`.
* **FSM States scattered:** All `StatesGroup` definitions (`OrderState`, `ProfileState`) are inline with handlers. Centralize them in `core/states.py`.

## 4. Redundancy Sweeper (Logic Centralization)
* **Aiogram Callback Guard:** The block `if not query.message or not hasattr(query.message, "edit_text"): return` is copied 20+ times across the codebase. Centralize into an Aiogram Middleware: `middlewares/callback_guard.py`.
* **Vault ID Normalization:** Duplicated across `authController.ts`. Centralize into `app_server/utils/formatters.ts`.
* **Pagination Math:** Page calculation is duplicated between `main_menu.py` and `transaction_history.py`. Create a `calculate_pagination` helper in `utils/helpers.py`.
* **Admin Verification:** `is_admin(user_id)` is duplicated across 4 different admin panels. Move to a centralized `utils/permissions.py`.
