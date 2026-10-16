"""
u:find Calendar Fetcher with SQLite TTL Caching.
Queries official university iCalendar endpoints for specified building and room terms.
"""
import urllib.parse
import logging
from typing import Optional
try:
    import httpx
except ImportError:
    httpx = None
import urllib.request
from app.db import get_cached_calendar, set_cached_calendar

logger = logging.getLogger(__name__)

UFIND_CALENDAR_BASE = "https://m2-ufind.univie.ac.at/courses/calendar/query.ics"
CACHE_TTL_SECONDS = 6 * 3600  # 6 hours cache per room


async def fetch_room_calendar(query_str: str, force_refresh: bool = False) -> str:
    """
    Fetches the .ics calendar data for a given room query string.
    Checks the local SQLite cache first unless force_refresh is True.
    """
    cache_key = f"query:{query_str.strip().lower()}"
    
    if not force_refresh:
        cached = get_cached_calendar(cache_key, max_age_seconds=CACHE_TTL_SECONDS)
        if cached:
            logger.debug(f"Cache hit for room query '{query_str}'")
            return cached

    encoded_query = urllib.parse.quote_plus(query_str)
    url = f"{UFIND_CALENDAR_BASE}?query={encoded_query}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; UnivieRoomLookup/1.0)",
        "Accept": "text/calendar, text/plain, */*"
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200 and "BEGIN:VCALENDAR" in resp.text:
                set_cached_calendar(cache_key, resp.text)
                logger.info(f"Fetched and cached fresh calendar for '{query_str}' ({len(resp.text)} bytes)")
                return resp.text
            else:
                logger.warning(f"u:find returned status {resp.status_code} for query '{query_str}'")
    except Exception as e:
        logger.error(f"Error fetching calendar for query '{query_str}': {e}")
        # Stale cache fallback if network fails
        stale = get_cached_calendar(cache_key, max_age_seconds=7 * 86400)
        if stale:
            logger.info(f"Returning stale cache for '{query_str}' due to network error")
            return stale
            
    return ""
