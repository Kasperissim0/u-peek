"""
FastAPI Server for UniWien Room Lookup.
Serves mobile-first web interface and REST API endpoints.
"""
import os
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Query, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.db import init_db
from app.catalog import (
    seed_database_if_empty,
    get_all_campuses,
    get_rooms_for_campus,
    get_room_details,
    sync_rooms_from_directory,
    check_auto_sync_needed,
)
from app.fetcher import fetch_campus_calendar
from app.analyzer import analyze_room_status, VIENNA_TZ

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("room_lookup")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Initialize SQLite tables and seed data
    init_db()
    seed_database_if_empty()
    logger.info("Database initialized and seeded.")
    
    # 2. Check if monthly room directory sync is due
    try:
        await check_auto_sync_needed()
    except Exception as e:
        logger.warning(f"Background room check warning: {e}")
        
    yield


app = FastAPI(title="u:peek • Univie Room Lookup", version="1.0.0", lifespan=lifespan)

# Allow CORS for mobile web or third-party callers
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static directory for assets (logos, icons)
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Serves the Zuckerborg logo as favicon."""
    favicon_path = os.path.join(os.path.dirname(__file__), "static", "zuckerborg.jpg")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path, media_type="image/jpeg")
    return HTMLResponse(status_code=404)


@app.get("/", response_class=HTMLResponse)
async def serve_home():
    """Serves the single-page responsive mobile web UI."""
    template_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()
    return HTMLResponse(content=html)


@app.get("/health")
async def health_check():
    """Healthcheck endpoint for Render / Fly.io / monitoring."""
    return {"status": "ok", "timestamp": datetime.now(VIENNA_TZ).isoformat()}


@app.get("/api/campuses")
async def list_campuses():
    """Returns available university campuses/buildings."""
    return get_all_campuses()


@app.get("/api/campuses/{campus_id}/rooms")
async def list_rooms(campus_id: str):
    """Returns all rooms belonging to a specific campus."""
    rooms = get_rooms_for_campus(campus_id)
    return rooms


@app.get("/api/status")
async def get_room_occupancy(
    campus: str = Query(..., description="Campus ID, e.g. w29"),
    room: str = Query(..., description="Room ID, e.g. hs1"),
    time: Optional[str] = Query(None, description="ISO datetime string, e.g. 2026-10-16T14:30"),
    refresh: bool = Query(False, description="Force refresh calendar cache")
):
    """
    Evaluates whether the specified room is currently occupied or free,
    returning current and upcoming course details.
    """
    room_info = get_room_details(campus, room)
    if not room_info:
        raise HTTPException(status_code=404, detail=f"Room '{room}' not found in campus '{campus}'")

    # Determine target datetime in Vienna timezone
    if time:
        try:
            # Parses ISO format (e.g. 2026-10-16T14:30 or 2026-10-16T14:30:00)
            cleaned = time.replace("Z", "")
            target_dt = datetime.fromisoformat(cleaned)
            if target_dt.tzinfo is None:
                if hasattr(VIENNA_TZ, 'localize'):
                    target_dt = VIENNA_TZ.localize(target_dt)
                else:
                    target_dt = target_dt.replace(tzinfo=VIENNA_TZ)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid time format: {e}")
    else:
        target_dt = datetime.now(VIENNA_TZ)

    # Fetch full timetable feed for this campus / SPLs (using 6-hour SQLite cache)
    ics_data = await fetch_campus_calendar(
        campus_id=campus,
        query_prefix=room_info["query_prefix"],
        spl_codes=room_info.get("spl_codes", ""),
        force_refresh=refresh
    )
    
    # Analyze schedule collision
    analysis = analyze_room_status(
        ics_content=ics_data,
        target_time=target_dt,
        room_label=room_info["label"],
        room_query=room_info["query_term"]
    )
    
    analysis["campus_id"] = campus
    analysis["campus_name"] = room_info["campus_name"]
    return analysis


@app.post("/api/rooms/sync")
async def trigger_room_sync(background_tasks: BackgroundTasks):
    """Triggers an update of the room directory from event.univie.ac.at."""
    result = await sync_rooms_from_directory()
    return result


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
