"""
Schedule & Timeline Analyzer.
Parses RFC 5545 iCalendar events and detects room collision/occupancy
for any given datetime in Vienna time.
"""
import re
import urllib.parse
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

try:
    from zoneinfo import ZoneInfo
    VIENNA_TZ = ZoneInfo("Europe/Vienna")
except ImportError:
    import pytz
    VIENNA_TZ = pytz.timezone("Europe/Vienna")

GERMAN_WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]


def build_ufind_highlight_url(url: str, location: str, event_dt: Optional[datetime] = None) -> str:
    """
    Builds a u:find URL equipped with a W3C Text Fragment (#:~:text=...)
    to scroll to and visually highlight the specific event entry in the browser.
    
    Uses W3C Text Fragment range with context:
    - prefix: German weekday (e.g., Montag-,)
    - textStart: Date (e.g., 19.10.)
    - textEnd: Room Location (e.g., Hörsaal 2, Währinger Straße 29 2.OG)
    
    This avoids table-cell block boundary collisions in Chromium and skips
    the top course summary header to highlight the exact table entry.
    Example:
    https://ufind.univie.ac.at/de/course.html?lv=052612&semester=2026W#gr1:~:text=Montag-,19.10.,H%C3%B6rsaal%202%2C%20W%C3%A4hringer%20Stra%C3%9Fe%2029%202.OG
    """
    if not url:
        return ""
    if not location:
        return url
        
    base_url = url.split(":~:text=")[0]
    clean_loc = location.replace('\\,', ',').replace('\n', ' ').strip()
    encoded_loc = urllib.parse.quote(clean_loc, safe='')
    
    if event_dt:
        weekday = GERMAN_WEEKDAYS[event_dt.weekday()]
        date_str = f"{event_dt.day:02d}.{event_dt.month:02d}."
        prefix = urllib.parse.quote(weekday, safe='')
        text_start = urllib.parse.quote(date_str, safe='')
        fragment = f":~:text={prefix}-,{text_start},{encoded_loc}"
    else:
        fragment = f":~:text={encoded_loc}"
        
    if "#" in base_url:
        return f"{base_url}{fragment}"
    else:
        return f"{base_url}#{fragment}"


def parse_ics_datetime(dt_str: str) -> Optional[datetime]:
    """
    Parses ICS datetime formats, e.g.:
    - 20261001T094500
    - 20261001T094500Z
    """
    dt_clean = dt_str.strip().replace("Z", "")
    match = re.match(r'^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})$', dt_clean)
    if not match:
        return None
    
    year, month, day, hour, minute, second = map(int, match.groups())
    dt = datetime(year, month, day, hour, minute, second)
    
    # Localize to Europe/Vienna
    if hasattr(VIENNA_TZ, 'localize'):
        return VIENNA_TZ.localize(dt)
    return dt.replace(tzinfo=VIENNA_TZ)


def parse_ics_events(ics_content: str, filter_room: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Parses all VEVENT blocks in an .ics feed.
    Optionally ensures the event LOCATION contains the specified room query term.
    """
    events = []
    
    # Split by VEVENT
    raw_events = re.findall(r'BEGIN:VEVENT(.*?)END:VEVENT', ics_content, re.DOTALL)
    
    for raw in raw_events:
        # Unfold lines (RFC 5545 line continuation begins with space/tab)
        unfolded = re.sub(r'\r?\n[ \t]', '', raw)
        
        # Extract DTSTART
        start_match = re.search(r'DTSTART(?:;[^:]+)?:(\d{8}T\d{6}Z?)', unfolded)
        # Extract DTEND
        end_match = re.search(r'DTEND(?:;[^:]+)?:(\d{8}T\d{6}Z?)', unfolded)
        # Extract SUMMARY
        summary_match = re.search(r'SUMMARY:(.*?)(?:\r?\n|$)', unfolded)
        # Extract LOCATION
        location_match = re.search(r'LOCATION:(.*?)(?:\r?\n|$)', unfolded)
        # Extract URL
        url_match = re.search(r'URL(?:;[^:]+)?:(https?://[^\s\r\n]+)', unfolded)
        
        if not (start_match and end_match and summary_match):
            continue
            
        start_dt = parse_ics_datetime(start_match.group(1))
        end_dt = parse_ics_datetime(end_match.group(1))
        
        if not (start_dt and end_dt):
            continue
            
        summary = summary_match.group(1).replace(r'\,', ',').strip()
        location = location_match.group(1).replace(r'\,', ',').strip() if location_match else ""
        url = url_match.group(1).strip() if url_match else ""
        
        # If room filter provided, ensure location matches
        if filter_room:
            # Normalize for matching (e.g. "Hörsaal 1" vs "Hörsaal 1\, Währinger")
            norm_filter = re.sub(r'[^a-zA-Z0-9]', '', filter_room.lower())
            norm_loc = re.sub(r'[^a-zA-Z0-9]', '', location.lower())
            if norm_filter and norm_filter not in norm_loc:
                continue

        # Parse Course Code, Type, and Name from Summary (e.g., "051040-1 VU Software Engineering 1")
        course_code = ""
        course_type = ""
        course_title = summary
        
        code_match = re.match(r'^([0-9]{5,6}(?:-[0-9]+)?)\s+([A-Z]{2,3})\s+(.*)$', summary)
        if code_match:
            course_code = code_match.group(1)
            course_type = code_match.group(2)
            course_title = code_match.group(3)

        events.append({
            "start": start_dt,
            "end": end_dt,
            "summary": summary,
            "title": course_title,
            "code": course_code,
            "type": course_type,
            "location": location,
            "url": url,
        })
        
    return sorted(events, key=lambda x: x["start"])


def analyze_room_status(ics_content: str, target_time: datetime, room_label: str, room_query: str) -> Dict[str, Any]:
    """
    Evaluates room occupancy for a specific target datetime.
    Returns whether the room is FREE or OCCUPIED, the current course (if any),
    and the next course scheduled.
    """
    events = parse_ics_events(ics_content, filter_room=room_query)
    
    current_course = None
    next_course = None
    
    for ev in events:
        if ev["start"] <= target_time < ev["end"]:
            current_course = ev
            break
            
    # Find next upcoming event starting strictly after target_time
    for ev in events:
        if ev["start"] > target_time:
            # If currently occupied, pick the next event after current ends
            if current_course and ev["start"] < current_course["end"]:
                continue
            next_course = ev
            break

    # Format output
    result = {
        "room_label": room_label,
        "target_time": target_time.strftime("%Y-%m-%d %H:%M"),
        "is_occupied": current_course is not None,
        "status": "OCCUPIED" if current_course else "FREE",
        "current_course": None,
        "next_course": None,
        "free_until": None,
        "remaining_minutes": None,
    }
    
    if current_course:
        mins_left = max(0, int((current_course["end"] - target_time).total_seconds() // 60))
        result["remaining_minutes"] = mins_left
        result["current_course"] = {
            "title": current_course["title"],
            "code": current_course["code"],
            "type": current_course["type"],
            "start": current_course["start"].strftime("%H:%M"),
            "end": current_course["end"].strftime("%H:%M"),
            "date": current_course["start"].strftime("%Y-%m-%d"),
            "location": current_course["location"],
            "url": build_ufind_highlight_url(current_course["url"], current_course["location"], current_course["start"]),
            "ends_in": f"{mins_left} min" if mins_left < 60 else f"{mins_left // 60}h {mins_left % 60}m",
        }
        
    if next_course:
        mins_until = max(0, int((next_course["start"] - target_time).total_seconds() // 60))
        result["free_until"] = next_course["start"].strftime("%H:%M")
        result["next_course"] = {
            "title": next_course["title"],
            "code": next_course["code"],
            "type": next_course["type"],
            "start": next_course["start"].strftime("%H:%M"),
            "end": next_course["end"].strftime("%H:%M"),
            "date": next_course["start"].strftime("%Y-%m-%d"),
            "location": next_course["location"],
            "url": build_ufind_highlight_url(next_course["url"], next_course["location"], next_course["start"]),
            "starts_in": f"in {mins_until} min" if mins_until < 60 else f"in {mins_until // 60}h {mins_until % 60}m"
        }
        
    return result
