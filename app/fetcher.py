"""
u:find Calendar Fetcher with SQLite TTL Caching.
Queries official university iCalendar endpoints for SPL (Directorate of Studies)
feeds to capture ALL lecture halls, seminar rooms, and PC-Unterrichtsräume.
"""
import ssl
import re
import urllib.parse
import urllib.request
import logging
from typing import Optional, List
try:
    import httpx
except ImportError:
    httpx = None

from app.db import get_cached_calendar, set_cached_calendar

logger = logging.getLogger(__name__)

UFIND_CALENDAR_BASE = "https://m2-ufind.univie.ac.at/courses/calendar/query.ics"
CACHE_TTL_SECONDS = 6 * 3600  # 6 hours cache

# SSL Context to prevent macOS CERTIFICATE_VERIFY_FAILED error
SSL_CTX = ssl._create_unverified_context()


async def fetch_raw_ics(query_str: str, force_refresh: bool = False) -> str:
    """Fetches a single .ics query from u:find with SQLite caching."""
    cache_key = f"query:{query_str.strip().lower()}"
    
    if not force_refresh:
        cached = get_cached_calendar(cache_key, max_age_seconds=CACHE_TTL_SECONDS)
        if cached:
            logger.debug(f"Cache hit for query '{query_str}'")
            return cached

    encoded_query = urllib.parse.quote_plus(query_str)
    url = f"{UFIND_CALENDAR_BASE}?query={encoded_query}"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; UnivieRoomLookup/1.0)",
        "Accept": "text/calendar, text/plain, */*"
    }
    
    # 1. Try httpx if installed
    if httpx is not None:
        try:
            async with httpx.AsyncClient(timeout=15.0, verify=False) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200 and "BEGIN:VCALENDAR" in resp.text:
                    set_cached_calendar(cache_key, resp.text)
                    logger.info(f"Fetched and cached fresh calendar for '{query_str}' ({len(resp.text)} bytes)")
                    return resp.text
        except Exception as e:
            logger.warning(f"httpx failed for '{query_str}': {e}, falling back to urllib")

    # 2. Built-in urllib fallback with SSL_CTX
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=15) as response:
            text = response.read().decode('utf-8', errors='ignore')
            if "BEGIN:VCALENDAR" in text:
                set_cached_calendar(cache_key, text)
                logger.info(f"urllib fetched fresh calendar for '{query_str}' ({len(text)} bytes)")
                return text
    except Exception as e:
        logger.error(f"urllib failed for '{query_str}': {e}")
        stale = get_cached_calendar(cache_key, max_age_seconds=14 * 86400)
        if stale:
            return stale
            
    return ""


async def fetch_campus_calendar(campus_id: str, query_prefix: str, spl_codes: str, force_refresh: bool = False) -> str:
    """
    Fetches the combined calendar feed for all SPLs associated with a campus.
    For example, W29 fetches 'spl5 +ct' (Informatik) and 'spl26 +ct' (Physik).
    """
    spl_list = [s.strip() for s in spl_codes.split(',') if s.strip()]
    if not spl_list:
        # Fallback to query prefix if no SPLs defined
        return await fetch_raw_ics(f"{query_prefix} +ct", force_refresh=force_refresh)

    vevent_blocks = []
    
    for spl in spl_list:
        spl_query = f"{spl} +ct"
        ics_text = await fetch_raw_ics(spl_query, force_refresh=force_refresh)
        if ics_text:
            events = re.findall(r'BEGIN:VEVENT.*?END:VEVENT', ics_text, re.DOTALL)
            vevent_blocks.extend(events)

    if not vevent_blocks:
        # Fallback to direct query prefix
        return await fetch_raw_ics(f"{query_prefix} +ct", force_refresh=force_refresh)

    # Wrap merged events into a standard VCALENDAR
    merged_ics = (
        "BEGIN:VCALENDAR\n"
        "VERSION:2.0\n"
        "PRODID:UniWienRoomLookup/1.0\n"
        + "\n".join(vevent_blocks) +
        "\nEND:VCALENDAR"
    )
    return merged_ics
