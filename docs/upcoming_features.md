# 🚀 Insta Vault - Upcoming Features & Architecture Backlog

This document tracks all features, flows, and structural updates that are planned for future development phases. These are **not** considered bugs in the current code, but rather missing capabilities that will be built later.

---

### 1. Daily Mission App Integration (Formerly BUG-015)
- **Status:** Planned for later.
- **Details:** The "Daily Mission" currently shows a 400 Spark reward but has no backend logic. In the future, this will be integrated with an APK download flow. Users will complete the mission (e.g., install the app) and then the Sparks will be credited.

### 2. Order Completion Flow & Stats Update (Formerly BUG-016 & BUG-017)
- **Status:** Planned for when the full order delivery system is built.
- **Details:** 
  - `total_views_recv`: Should only increment when the views are *actually delivered* (order completed), not immediately when the order is placed.
  - `first_order_date`: Will be set correctly when the complete order flow is built.

### 4. User Rank Tier System (Formerly BUG-018)
- **Status:** Planned for later development phase.
- **Details:** Currently, all users are hardcoded as "Rookie Vaulter". A backend worker or transaction logic needs to be implemented to update `rank_tier` dynamically as `lifetime_sparks` increases.


### 5. Full Delivery Tracking System
- **Status:** Planned for next major update.
- **Details:** After an order is confirmed and Sparks are deducted, the system needs an integration (like an SMM Panel API) to track live order delivery status and update users accordingly.

### 6. Viral Growth & Advanced Referral UI
- **Status:** Planned for next major update.
- **Details:** The current referral system works well technically. Future updates will focus on "Viral Growth UI" (e.g., beautiful shareable referral cards, "Invite 5 friends to unlock X" progress bars, and top-referrer leaderboards) to maximize user acquisition.
