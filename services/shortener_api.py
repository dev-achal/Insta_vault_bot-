"""
services/shortener_api.py
~~~~~~~~~~~~~~~~~~~~~~~~~
GPLinks Shortener API Client.

Used by the Shortlink Mission to generate short URLs that redirect
users through GPLinks ads before returning to the bot via deep-link.

API Docs: GET https://api.gplinks.com/api?api=TOKEN&url=DESTINATION
Response: {"status":"success","shortenedUrl":"https://gplinks.com/xxxxx"}
"""

import logging

import aiohttp

import config

logger = logging.getLogger(__name__)


class ShortenerApiError(Exception):
    """Raised when the GPLinks API returns an error or is unreachable."""
    pass


async def create_short_link(destination_url: str) -> str:
    """Shorten a URL via GPLinks API.

    Args:
        destination_url: The bot deep-link URL to shorten
                         (e.g., "https://t.me/BotName?start=sl_abc123").

    Returns:
        The shortened URL string (e.g., "https://gplinks.com/xxxxx").

    Raises:
        ShortenerApiError: If API credentials are missing, network fails,
                          or GPLinks returns an error response.
    """
    if not config.GPLINKS_API_URL or not config.GPLINKS_API_KEY:
        raise ShortenerApiError(
            "GPLINKS_API_URL and GPLINKS_API_KEY must be set in .env"
        )

    params = {
        "api": config.GPLINKS_API_KEY,
        "url": destination_url,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                config.GPLINKS_API_URL,
                params=params,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                # Guard against non-200 responses (Cloudflare, rate limits, server errors)
                if resp.status != 200:
                    error_text = await resp.text()
                    raise ShortenerApiError(
                        f"GPLinks HTTP {resp.status}: {error_text[:200]}"
                    )

                data = await resp.json(content_type=None)

                if not isinstance(data, dict):
                    raise ShortenerApiError(f"Unexpected response type: {data}")

                if data.get("status") == "error":
                    raise ShortenerApiError(
                        f"GPLinks error: {data.get('message', 'Unknown')}"
                    )

                short_url = data.get("shortenedUrl")
                if not short_url:
                    raise ShortenerApiError(
                        f"No shortenedUrl in response: {data}"
                    )

                logger.info(
                    "GPLinks shortened: %s → %s",
                    destination_url, short_url,
                )
                return short_url

    except aiohttp.ClientError as e:
        logger.error("GPLinks network error: %s", e, exc_info=True)
        raise ShortenerApiError(f"Network error: {e}") from e
    except ShortenerApiError:
        raise
    except Exception as e:
        logger.error("GPLinks unexpected error: %s", e, exc_info=True)
        raise ShortenerApiError(f"Unexpected error: {e}") from e
