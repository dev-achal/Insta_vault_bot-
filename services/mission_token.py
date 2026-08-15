"""
services/mission_token.py
~~~~~~~~~~~~~~~~~~~~~~~~~
Redis-backed mission token lifecycle: create, verify, consume.

Token Storage Pattern:
  Key:   task:shortener:<token>    → Value: <user_id>   (TTL: 30 min)
  Key:   pending:shortener:<uid>  → Value: <token>      (TTL: 30 min)

Security:
  - GETDEL for atomic verify+consume (prevents double-spend)
  - user_id match check (prevents token hijacking)
  - TTL auto-expiry (prevents stale token abuse)
  - pending key prevents duplicate token generation spam
"""

import logging
import secrets

from database.redis_manager import get_redis
import config

logger = logging.getLogger(__name__)

TOKEN_PREFIX = "task:shortener:"
PENDING_PREFIX = "pending:shortener:"


async def create_token(user_id: int) -> str:
    """Generate a unique shortener mission token and store in Redis.

    Creates two keys:
      1. task:shortener:sl_xxx → user_id   (for verification on deep-link return)
      2. pending:shortener:uid → sl_xxx    (to prevent duplicate token generation)

    Both keys share the same TTL so they expire together.
    """
    token = f"sl_{secrets.token_hex(12)}"
    redis = get_redis()
    ttl = config.SHORTENER_TOKEN_TTL

    # Store the token → user_id mapping
    await redis.setex(f"{TOKEN_PREFIX}{token}", ttl, str(user_id))

    # Mark this user as having a pending token
    await redis.setex(f"{PENDING_PREFIX}{user_id}", ttl, token)

    logger.info(
        "Shortener token created: %s for user %s (TTL=%ds)",
        token, user_id, ttl,
    )
    return token


async def get_pending_token(user_id: int) -> str | None:
    """Check if user already has a pending (unused) shortener token.

    Returns the token string if found, None otherwise.
    Used to prevent spamming multiple token generations.
    """
    redis = get_redis()
    return await redis.get(f"{PENDING_PREFIX}{user_id}")


async def verify_and_consume(token: str, user_id: int) -> bool:
    """Verify token exists, belongs to user, and consume it atomically.

    Uses Redis GETDEL for atomic read+delete (prevents double-spend).
    Also cleans up the pending marker on success.

    Returns:
        True if valid and consumed, False otherwise.
    """
    redis = get_redis()
    key = f"{TOKEN_PREFIX}{token}"

    # Atomic get-and-delete — if two requests arrive simultaneously,
    # only the first will get the value; the second gets None.
    stored_user_id = await redis.getdel(key)

    if stored_user_id is None:
        logger.warning("Shortener token not found/expired: %s", token)
        return False

    if str(stored_user_id) != str(user_id):
        logger.warning(
            "Shortener token hijack attempt: %s belongs to %s, claimed by %s",
            token, stored_user_id, user_id,
        )
        return False

    # Clean up the pending marker
    await redis.delete(f"{PENDING_PREFIX}{user_id}")

    logger.info(
        "Shortener token verified+consumed: %s for user %s",
        token, user_id,
    )
    return True
