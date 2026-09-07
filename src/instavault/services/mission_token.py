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

from instavault.database.redis_manager import get_redis
from instavault.core import config
from instavault.constants import rewards

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
    ttl = rewards.SHORTENER_TOKEN_TTL

    # Store the token → user_id mapping
    await redis.setex(f"{TOKEN_PREFIX}{token}", ttl, str(user_id))

    # Mark this user as having a pending token
    await redis.setex(f"{PENDING_PREFIX}{user_id}", ttl, token)

    logger.info(
        "Shortener token created: %s for user %s (TTL=%ds)",
        token,
        user_id,
        ttl,
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
            token,
            stored_user_id,
            user_id,
        )
        return False

    # Clean up the pending marker
    await redis.delete(f"{PENDING_PREFIX}{user_id}")

    logger.info(
        "Shortener token verified+consumed: %s for user %s",
        token,
        user_id,
    )
    return True


# ===========================================================================
# QUIZ MISSION TOKENS — Same pattern, different namespace
# ===========================================================================

QUIZ_TOKEN_PREFIX = "task:quiz:"
QUIZ_PENDING_PREFIX = "pending:quiz:"


async def create_quiz_token(user_id: int) -> str:
    """Generate a unique quiz mission token and store in Redis.

    Creates two keys:
      1. task:quiz:qz_xxx → user_id   (for verification on deep-link return)
      2. pending:quiz:uid → qz_xxx    (to prevent duplicate token generation)

    Both keys share the same TTL so they expire together.
    """
    token = f"qz_{secrets.token_hex(12)}"
    redis = get_redis()
    ttl = rewards.QUIZ_TOKEN_TTL

    # Store the token → user_id mapping
    await redis.setex(f"{QUIZ_TOKEN_PREFIX}{token}", ttl, str(user_id))

    # Mark this user as having a pending quiz token
    await redis.setex(f"{QUIZ_PENDING_PREFIX}{user_id}", ttl, token)

    logger.info(
        "Quiz token created: %s for user %s (TTL=%ds)",
        token,
        user_id,
        ttl,
    )
    return token


async def get_pending_quiz_token(user_id: int) -> str | None:
    """Check if user already has a pending (unused) quiz token."""
    redis = get_redis()
    return await redis.get(f"{QUIZ_PENDING_PREFIX}{user_id}")


async def verify_and_consume_quiz(token: str, user_id: int) -> bool:
    """Verify quiz token exists, belongs to user, and consume atomically.

    Uses Redis GETDEL for atomic read+delete (prevents double-spend).
    Also cleans up the pending marker on success.

    Returns:
        True if valid and consumed, False otherwise.
    """
    redis = get_redis()
    key = f"{QUIZ_TOKEN_PREFIX}{token}"

    stored_user_id = await redis.getdel(key)

    if stored_user_id is None:
        logger.warning("Quiz token not found/expired: %s", token)
        return False

    if str(stored_user_id) != str(user_id):
        logger.warning(
            "Quiz token hijack attempt: %s belongs to %s, claimed by %s",
            token,
            stored_user_id,
            user_id,
        )
        return False

    # Clean up the pending marker
    await redis.delete(f"{QUIZ_PENDING_PREFIX}{user_id}")

    logger.info(
        "Quiz token verified+consumed: %s for user %s",
        token,
        user_id,
    )
    return True


# ===========================================================================
# VERIFY-ONLY TOKENS — Human check on daily limit (no reward)
# ---------------------------------------------------------------------------
# Used when a user hits the daily limit on games (Coin Flip, Quiz, etc.).
# Instead of directly showing "limit reached", we ask them to verify
# they're human via a shortener link. After verification, the bot
# shows the daily limit message.
#
# Token prefix: vf_
# No reward is granted — this is purely for ad monetization + anti-bot.
# ===========================================================================

VERIFY_TOKEN_PREFIX = "task:verify:"
VERIFY_PENDING_PREFIX = "pending:verify:"
VERIFY_TOKEN_TTL = 1800  # 30 minutes


async def create_verify_token(user_id: int) -> str:
    """Generate a verify-only token for human verification.

    Unlike quiz/shortener tokens, this grants NO reward.
    It only forces the user through the shortener ad flow
    before showing the daily limit message.
    """
    token = f"vf_{secrets.token_hex(12)}"
    redis = get_redis()

    await redis.setex(f"{VERIFY_TOKEN_PREFIX}{token}", VERIFY_TOKEN_TTL, str(user_id))
    await redis.setex(f"{VERIFY_PENDING_PREFIX}{user_id}", VERIFY_TOKEN_TTL, token)

    logger.info(
        "Verify token created: %s for user %s (TTL=%ds)",
        token, user_id, VERIFY_TOKEN_TTL,
    )
    return token


async def get_pending_verify_token(user_id: int) -> str | None:
    """Check if user already has a pending verify token."""
    redis = get_redis()
    return await redis.get(f"{VERIFY_PENDING_PREFIX}{user_id}")


async def verify_and_consume_verify(token: str, user_id: int) -> bool:
    """Verify token exists, belongs to user, and consume atomically.

    Returns True if valid and consumed, False otherwise.
    No reward is granted — caller just shows the daily limit message.
    """
    redis = get_redis()
    key = f"{VERIFY_TOKEN_PREFIX}{token}"

    stored_user_id = await redis.getdel(key)

    if stored_user_id is None:
        logger.warning("Verify token not found/expired: %s", token)
        return False

    if str(stored_user_id) != str(user_id):
        logger.warning(
            "Verify token hijack attempt: %s belongs to %s, claimed by %s",
            token, stored_user_id, user_id,
        )
        return False

    await redis.delete(f"{VERIFY_PENDING_PREFIX}{user_id}")

    logger.info(
        "Verify token verified+consumed: %s for user %s",
        token, user_id,
    )
    return True
