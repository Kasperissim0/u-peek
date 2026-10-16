# UniWien Room Lookup (u:find)

A lightweight, mobile-first web app and API that tells you which course is taking place in a University of Vienna lecture hall or seminar room at any given time (defaults to **Währinger Straße 29** and the **current time**).

## Features
* **Mobile-First Interface**: Quick-tap buttons for lecture halls (`HS 1`, `HS 2`, `HS 3`) and seminar rooms (`SR 1`–`SR 12`) without typing.
* **Campus & Time Picker**: Defaults to Währinger Straße 29 and current Vienna time, with easy toggling for other dates/times or campuses (OMP, Hauptgebäude, Altes AKH).
* **Live Schedule & Vacancy**: Shows currently active course, instructor, time remaining, link to u:find, and next scheduled course.
* **Smart Hybrid Caching**: Caches `.ics` feeds in SQLite for 6 hours to avoid spamming university servers, achieving <5ms response times.
* **Dynamic Room Discovery**: Periodically auto-syncs newly renovated, added, or renamed rooms from `event.univie.ac.at/services/raumuebersicht` once a month.
* **Zero Credentials**: Uses 100% public u:find endpoints—no student logins or password storage required.

---

## 1. Running Locally on your Mac

1. **Activate virtual environment & install requirements**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Start the server**:
   ```bash
   python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

3. **Open on Computer**:
   Visit `http://localhost:8000`.

4. **Open on your Phone (Same Wi-Fi)**:
   * Find your Mac's local IP address (e.g. `192.168.1.150` via System Settings > Wi-Fi > Details).
   * Open `http://192.168.1.150:8000` in Safari or Chrome on your phone.
   * Tap **Share > Add to Home Screen** on iOS Safari to use it like a native app.

---

## 2. Free Cloud Tier Deployment (Render)

To make it accessible from your phone 24/7 anywhere (even on mobile data outside home Wi-Fi):

1. Push this folder to a GitHub repository:
   ```bash
   git init
   git add .
   git commit -m "Initial commit of uniwien-room-lookup"
   git remote add origin <your-github-repo-url>
   git push -u origin main
   ```
2. Log in to [Render.com](https://render.com) (free).
3. Click **New + > Web Service** and select your GitHub repository.
4. Render will automatically detect the `Dockerfile` and `render.yaml`.
5. Click **Deploy Web Service** (Free plan).
6. In ~2 minutes, Render gives you a public HTTPS URL (e.g. `https://uniwien-rooms.onrender.com`) that you can open on your phone anywhere!

---

## 3. Migrating to Raspberry Pi (When it Arrives)

When your Raspberry Pi is ready:

### Option A: Direct Python (Lightest)
```bash
git clone <your-repo>
cd room-lookup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

To run it continuously in the background on reboot, create a systemd service `/etc/systemd/system/room-lookup.service`:
```ini
[Unit]
Description=UniWien Room Lookup
After=network.target

[Service]
User=pi
WorkingDirectory=/home/pi/room-lookup
ExecStart=/home/pi/room-lookup/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```
Enable and start it:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now room-lookup
```

### Option B: Docker
```bash
docker build -t room-lookup .
docker run -d -p 8000:8000 --restart always --name room-lookup room-lookup
```

---

## 4. REST API Endpoints

* `GET /api/campuses`: List available university campuses.
* `GET /api/campuses/{campus_id}/rooms`: List all rooms for a campus.
* `GET /api/status?campus=w29&room=hs1&time=2026-10-16T14:30`: Get occupancy status.
* `POST /api/rooms/sync`: Trigger manual room directory refresh from `event.univie.ac.at`.
* `GET /health`: Healthcheck endpoint.
