"""
handlers/admin/cache_stats.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Admin-only handler for the Cache & DB Performance monitoring dashboard.

Displays:
  §1 — Session-level cache hit/miss stats with visual progress bar
  §2 — Redis server info (memory, keys, uptime, version)
  §3 — Firestore impact estimation (misses = DB reads)

Data sources:
  • In-memory counters from ``db_manager._cache_stats`` (zero overhead)
  • Redis INFO / DBSIZE commands via ``redis_manager.get_redis_info()``
"""

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from instavault.core.config import ADMIN_IDS
from instavault.database.db_manager import get_cache_stats
from instavault.database.redis_manager import get_redis_info
from instavault.keyboards.admin import admin_back_keyboard

logger = logging.getLogger(__name__)
router = Router(name="admin_cache_stats")


# ===========================================================================
# §1  HELPER — Format seconds into human-readable duration
# ===========================================================================

def _fmt_duration(seconds: int | float) -> str:
    """Convert seconds to a human-readable 'Xd Xh Xm Xs' string."""
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    minutes, secs = divmod(s, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)

    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs and not days:  # skip seconds if days are shown
        parts.append(f"{secs}s")
    return " ".join(parts) or "0s"


# ===========================================================================
# §2  HELPER — Visual progress bar (20-block width)
# ===========================================================================

def _progress_bar(percentage: float) -> str:
    """Render a 20-block wide text progress bar.

    Example: ██████████████░░░░░░ 70.0%
    """
    filled = int(percentage / 5)   # 20 blocks max
    empty = 20 - filled
    return f"{'█' * filled}{'░' * empty} {percentage}%"


# ===========================================================================
# §3  HANDLER — 📊 Cache & DB Stats Button Click
# ---------------------------------------------------------------------------
# Admin clicks "📊 Cache & DB Stats" on the admin dashboard.
# Fetches in-memory cache stats + Redis server info and renders
# a professional monitoring dashboard.
# ===========================================================================

@router.callback_query(F.data == "admin_cache_stats")
async def cb_cache_stats(query: CallbackQuery) -> None:
    """Render the Cache & DB Performance monitoring dashboard."""
    if not query.from_user or query.from_user.id not in ADMIN_IDS:
        await query.answer("⛔ Admin only.", show_alert=True)
        return
    if not query.message or not hasattr(query.message, "edit_text"):
        await query.answer()
        return
    await query.answer()

    # ── 1. Fetch cache performance stats (in-memory, instant) ─────────
    stats = get_cache_stats()
    hits = stats["hits"]
    misses = stats["misses"]
    total = stats["total"]
    hit_rate = stats["hit_rate"]
    miss_rate = stats["miss_rate"]
    session_secs = stats["session_seconds"]

    # ── 2. Fetch Redis server info (1 pipeline round-trip) ────────────
    redis_info = await get_redis_info()
    mem_human = redis_info["memory_used_human"]
    total_keys = redis_info["total_keys"]
    redis_uptime = redis_info["uptime_seconds"]
    redis_ver = redis_info["redis_version"]

    # ── 3. Build the dashboard text ───────────────────────────────────
    text = (
        "📊 <b>CACHE & DB PERFORMANCE</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"

        f"⏱️ <b>Bot Session:</b> {_fmt_duration(session_secs)}\n\n"

        "🔄 <b>Request Stats:</b>\n"
        f"  ✅ Cache Hits:     <b>{hits:,}</b>\n"
        f"  ❌ Cache Misses:   <b>{misses:,}</b>\n"
        f"  📦 Total Requests: <b>{total:,}</b>\n\n"

        "📈 <b>Cache Hit Rate:</b>\n"
        f"  <code>{_progress_bar(hit_rate)}</code>\n\n"

        "🗄️ <b>Redis Server:</b>\n"
        f"  💾 Memory Used:     <b>{mem_human}</b>\n"
        f"  🔑 Active Keys:     <b>{total_keys:,}</b>\n"
        f"  ⏱️ Redis Uptime:    <b>{_fmt_duration(redis_uptime)}</b>\n"
        f"  🏷️ Redis Version:   <b>{redis_ver}</b>\n\n"

        "🔥 <b>Firestore Impact:</b>\n"
        f"  📖 DB Reads (misses): <b>{misses:,}</b>\n"
        "  💡 <i>Every cache miss = 1 Firestore read</i>\n"
        f"  💰 <i>Estimated cost: ~${misses * 0.00006:.4f}</i>\n\n"

        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "<i>🔄 Stats reset on bot restart</i>"
    )

    await query.message.edit_text(text, reply_markup=admin_back_keyboard())
