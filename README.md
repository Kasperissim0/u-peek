# u:peek (Univie Room Lookup)

A lightweight, mobile-first web app and API that lets you peek into any University of Vienna lecture hall, seminar room, or computer lab in real-time to see what is happening right now and next.

Defaults to **Währinger Straße 29** and the **current Vienna time**.

## Features
* **Mobile-First Interface**: Quick-tap buttons for lecture halls (`HS 1`, `HS 2`, `HS 3`), seminar rooms (`SR 1`–`SR 12`), and PC labs (`PC 1`–`PC 6`) without typing.
* **Campus & Time Picker**: Defaults to Währinger Straße 29 and current Vienna time, with easy toggling for other dates/times or campuses (Hauptgebäude, Campus Altes AKH, OMP, Juridicum, NIG, etc.).
* **Live Schedule & Vacancy**: Shows currently active course, instructor, time remaining, direct link to u:find, and next scheduled course.
* **Smart Hybrid Caching**: Caches `.ics` feeds in SQLite for 6 hours to avoid spamming university servers, achieving <5ms response times.
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
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

3. **Open on Computer**:
   Visit `http://localhost:8000`.

4. **Open on your Phone (Same Wi-Fi)**:
   * Find your Mac's local IP address (e.g. `http://192.168.1.xxx:8000`).
   * Open it on your phone and tap **Share > Add to Home Screen** on iOS Safari.

---

## 2. Deploying Online for Free on Koyeb (No Credit Card)

1. Sign up for free at [koyeb.com](https://www.koyeb.com) using your GitHub account.
2. Click **Create Service** > **GitHub**.
3. Select your repository `Kasperissim0/u-peek`.
4. Koyeb detects the `Dockerfile` automatically:
   * **Instance Type**: `Eco / Nano` (Free)
   * **Region**: `Frankfurt (fra)`
   * **Port**: `8000`
   * **Health Check Path**: `/health`
5. Click **Deploy**. In ~2 minutes, your permanent HTTPS URL is live!

---

## 3. Running on Raspberry Pi (Local Home Server)

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
