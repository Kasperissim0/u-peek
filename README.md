# u:peek • University of Vienna Room Lookup

> **Live Instance**: [https://u-peek.onrender.com](https://u-peek.onrender.com)  
> Mobile-first web app and API to instantly peek into any University of Vienna lecture hall, seminar room, or computer lab to see **what is happening right now and next**.

---

## Table of Contents
0. [Legal Notice & Disclaimers](#0-legal-notice--disclaimers)
1. [Core Features](#core-features)
2. [Data Pipeline & Architecture](#data-pipeline--architecture)
3. [Zero-Sleep Keep-Alive Configuration](#zero-sleep-keep-alive-configuration)
4. [Migration to Raspberry Pi / Local Server](#migration-to-raspberry-pi--local-server)
5. [Running Locally on macOS / Linux](#running-locally-on-macos--linux)
6. [REST API Reference](#rest-api-reference)

---

## 0. Legal Notice & Disclaimers

### Non-Affiliation Disclaimer
`u:peek` is an independent, non-commercial open-source student utility. It is **not** affiliated with, maintained, sponsored, or officially endorsed by the **University of Vienna** (*Universität Wien*). All trademarks, service marks, campus names, and building designations belong to their respective owners.

### Compliance with Austrian & European Union Law

1. **Public Statutory Data Access (Universitätsgesetz 2002 – UG §§ 79, 80)**:  
   Under the Austrian Universities Act (*UG 2002*), public universities are legally mandated to publish their course catalogs (*Vorlesungsverzeichnis*), examination dates, teaching locations, and designated instructors publicly for student transparency.

2. **Copyright & Factual Data (Austrian UrhG § 1)**:  
   Course codes, room numbers, dates, timetable intervals, and lecture locations constitute raw, non-copyrightable factual data under **§ 1 UrhG** (lacking *eigentümliche geistige Schöpfung* / individual creative expression).

3. **Text and Data Mining (EU Directive 2019/790 & Austrian UrhG § 42h)**:  
   Under the European Union Directive on Copyright in the Digital Single Market (implemented in **§ 42h UrhG**), automated processing and reading of lawfully accessible public content is explicitly permitted for legitimate informational purposes where no machine-readable opt-out exists.

4. **Database Rights (Directive 96/9/EC & CJEU Case Law)**:  
   According to consistent jurisprudence from the Court of Justice of the European Union (*CJEU C-203/02 British Horseracing Board* and *C-444/02 Fixtures Marketing*), data generated as a natural byproduct of core operational or statutory administrative activities does not qualify for *sui generis* database exclusivity.

5. **Open RFC 5545 Syndication Feeds & Robots.txt**:  
   `u:peek` queries the publicly accessible iCalendar feed (`m2-ufind.univie.ac.at/courses/calendar/query.ics`), which is deliberately exposed by the university for open external calendar subscriptions (RFC 5545). No login credentials, session cookies, or access-control barriers are bypassed. Crawler policies in `univie.ac.at/robots.txt` are strictly respected.

6. **Data Protection & GDPR (DSGVO Art. 6(1)(f))**:  
   Displaying public course instructors for classroom schedule verification falls under legitimate interest (**Art. 6(1)(f) DSGVO**). `u:peek` does **not** collect, store, index, or profile private individual contact data (no personal email addresses or phone numbers).

7. **Server Integrity & Responsible Caching (StGB § 126b)**:  
   To prevent server strain and uphold fair computing ethics, all fetched timetable blocks are cached locally in SQLite for **6 hours**. Direct requests to university infrastructure are strictly throttled and rate-limited.

---

## Core Features
* **Zero Typing Needed**: Instant quick-tap buttons for lecture halls (`HS 1`, `HS 2`, `HS 3`), seminar rooms (`SR 1`–`SR 12`), and PC labs (`PC 1`–`PC 6`).
* **Instant Occupancy & Details**: Displays whether the room is **FREE** or **OCCUPIED**, the active lecture title, group, lecturer, exact time remaining, and the next upcoming course.
* **All Faculties Included**: Comprehensive coverage across all University of Vienna locations (Währinger Straße 29, Hauptgebäude, Campus Altes AKH, OMP, Juridicum, NIG, UZA II, Djerassiplatz, etc.).
* **Smart Hybrid Caching**: Calendar feeds are parsed and cached in SQLite with Write-Ahead Logging (`PRAGMA journal_mode=WAL`) for 6 hours, delivering `<5ms` responses without spamming university servers.
* **Zero Credentials**: Powered entirely by public `u:find` calendar feeds—no student logins or tokens required.

---

## Data Pipeline & Architecture

```
                       ┌──────────────────────────────────────────────┐
                       │           University of Vienna               │
                       │  • event.univie.ac.at (Building Directory)   │
                       │  • m2-ufind.univie.ac.at (SPL .ics Feeds)    │
                       └──────────────────────┬───────────────────────┘
                                              │ (Automated Sync / 6h Cache)
                                              ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                   u:peek Engine                                     │
│                                                                                     │
│  1. Room Harvester                                                                  │
│     • Deterministically pulls teaching feeds (SPL 5, SPL 22, SPL 6, SPL 25, etc.)   │
│     • Parses comma-separated multi-room clauses & building keywords                 │
│     • Normalizes and deduplicates canonical room IDs (e.g. 'pc6', 'hs1')            │
│                                                                                     │
│  2. SQLite Storage (WAL Mode)                                                       │
│     • `campuses`: Standardized "Name: Location (Disciplines)" records               │
│     • `rooms`: Deduplicated lecture halls, seminar rooms, and computer labs         │
│     • `calendar_cache`: Raw .ics payloads + TTL for instant local replay            │
│                                                                                     │
│  3. Real-Time Occupancy Analyzer                                                    │
│     • Queries live room schedule from cached/remote .ics feed                       │
│     • Normalizes recurring timezone offsets (`Europe/Vienna`)                       │
│     • Evaluates current status: OCCUPIED (with countdown) vs. FREE (until next)     │
└─────────────────────────────────────────────┬───────────────────────────────────────┘
                                              │ REST API / JSON (<5ms)
                                              ▼
                        ┌───────────────────────────────────────────┐
                        │              Client UI / PWA              │
                        │  • Tailwind CSS Dark UI                   │
                        │  • Real-time Vienna clock                 │
                        │  • iOS & Android "Add to Home Screen"     │
                        └───────────────────────────────────────────┘
```

### How Occupancy is Determined
1. **Target Room Resolution**: The user selects a campus (`w29`) and room (`hs1`), optionally picking a custom timestamp (default: current Vienna time).
2. **Authoritative Calendar Fetching**: The engine requests the `.ics` calendar feed for the room using the campus SPL codes and room query terms.
3. **Event Window Analysis**:
   - Compares target time $T$ against each event interval $[DTSTART, DTEND]$.
   - If an event covers $T$, status is set to `OCCUPIED`, returning the course code, title, instructor, and minutes remaining until $DTEND$.
   - The engine searches forward for the earliest event starting after $T$ to display what is coming next (`Starts at HH:MM`).
   - If no event is active, status is `FREE` and reports how long the room remains empty until the next scheduled lecture.

---

## Zero-Sleep Keep-Alive Configuration

Render's free tier spins down containers after 15 minutes of inactivity, resulting in a ~45-50 second cold start on the first visit. 

You can eliminate cold starts entirely using a free uptime monitor:

### Setup with cron-job.org (Free Forever, No Card Required)
1. Sign up for a free account at [cron-job.org](https://cron-job.org).
2. Click **Create Cronjob**.
3. Configure the job:
   * **Title**: `u:peek Keep-Alive`
   * **URL**: `https://u-peek.onrender.com/health`
   * **Schedule**: **Every 10 minutes** (`*/10 * * * *`)
   * **Request Method**: `GET`
4. Click **Create**.

> **Result**: Render receives a ping every 10 minutes and never goes to sleep. Responses on phone and computer will always be **instant (0s cold start)**.

---

## Migration to Raspberry Pi / Local Server

`u:peek` is designed with **zero cloud dependencies** and runs natively on ARM64 Linux (Raspberry Pi 4 / 5, Libre Computer, or home servers).

### Method A: Docker Compose (Recommended)

1. **Clone the repository on your Raspberry Pi**:
   ```bash
   git clone https://github.com/Kasperissim0/u-peek.git
   cd u-peek
   ```

2. **Start the service in the background**:
   ```bash
   docker compose up -d
   ```
   * The container auto-builds using the multi-arch `Dockerfile` (`python:3.11-slim`).
   * Configured with `restart: unless-stopped`, so it resumes automatically after power outages or Pi reboots.

3. **Check logs**:
   ```bash
   docker compose logs -f
   ```

---

### Method B: Native Systemd Service (Ultra-Light, ~55MB RAM)

1. **Install dependencies on your Raspberry Pi**:
   ```bash
   sudo apt update && sudo apt install -y python3-venv git
   git clone https://github.com/Kasperissim0/u-peek.git /home/pi/u-peek
   cd /home/pi/u-peek
   python3 -m venv .venv
   .venv/bin/pip install --upgrade pip
   .venv/bin/pip install -r requirements.txt
   ```

2. **Create a systemd unit file**:
   ```bash
   sudo nano /etc/systemd/system/u-peek.service
   ```
   Paste the following:
   ```ini
   [Unit]
   Description=u:peek Univie Room Lookup Service
   After=network.target

   [Service]
   User=pi
   WorkingDirectory=/home/pi/u-peek
   ExecStart=/home/pi/u-peek/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
   Restart=always
   RestartSec=5
   Environment=PYTHONUNBUFFERED=1

   [Install]
   WantedBy=multi-user.target
   ```

3. **Enable and start the service**:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now u-peek
   ```

4. **Verify status**:
   ```bash
   sudo systemctl status u-peek
   ```

---

### Accessing your Raspberry Pi on Home Wi-Fi & Remotely

* **Local Network Access**: Open `http://<raspberrypi-ip>:8000` or `http://raspberrypi.local:8000` on your phone connected to the same Wi-Fi.
* **Remote Access Outside Home (Zero Port Forwarding)**:
  * **Option 1 (Cloudflare Tunnel - Free)**: Run `cloudflared tunnel` on the Pi to route a custom domain (or free Cloudflare hostname) directly to `http://localhost:8000` without exposing home ports.
  * **Option 2 (Tailscale - Free)**: Install Tailscale on your Pi and phone to connect securely via private mesh VPN from anywhere.

---

## Running Locally on macOS / Linux

```bash
# 1. Clone repository
git clone https://github.com/Kasperissim0/u-peek.git
cd u-peek

# 2. Setup virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Launch dev server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Open `http://localhost:8000` in your browser.

---

## REST API Reference

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/api/campuses` | `GET` | List all 13 University of Vienna faculties and campuses. |
| `/api/campuses/{campus_id}/rooms` | `GET` | Retrieve all lecture halls, seminar rooms, and PC labs for a campus. |
| `/api/status?campus={c}&room={r}&time={iso}` | `GET` | Get real-time room occupancy status, current course, and next event. |
| `/api/rooms/sync` | `POST` | Trigger background catalog refresh from university feeds. |
| `/health` | `GET` | Lightweight health check endpoint used by keep-alive monitors. |

### Example Status Response:
```json
{
  "campus": "Währinger Straße 29 (Computer Science & Media)",
  "room": "HS 1",
  "status": "OCCUPIED",
  "checked_time": "2026-10-16T13:45:00+02:00",
  "current_event": {
    "summary": "051031 VU Datenbanksysteme (2026W) - Gruppe 1",
    "course_id": "051031-1",
    "start": "2026-10-16T13:15:00+02:00",
    "end": "2026-10-16T14:45:00+02:00",
    "time_remaining_str": "Ends in 1h 0m",
    "ufind_url": "https://ufind.univie.ac.at/de/course.html?lv=051031&semester=2026W"
  },
  "next_event": {
    "summary": "051000 VO Technische Grundlagen der Informatik",
    "start": "2026-10-16T15:00:00+02:00",
    "starts_in_str": "Starts at 15:00"
  }
}
```
