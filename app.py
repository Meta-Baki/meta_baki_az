from flask import Flask, request, jsonify, send_from_directory
import json
import requests
import os
from datetime import datetime
from zoneinfo import ZoneInfo
import base64

app = Flask(__name__)

# ---------------- CONFIG ----------------
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO = "Meta-Baki/meta-weather"
FILE = "history.json"

BAKU_TZ = ZoneInfo("Asia/Baku")

DATA_FILE = "data.json"
HISTORY_FILE = "history.json"
LAST_SAVE_FILE = "last_save.json"


# ---------------- GITHUB PUSH ----------------
def update_github(history):
    url = f"https://api.github.com/repos/{REPO}/contents/{FILE}"

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }

    r = requests.get(url, headers=headers)
    sha = None
    if r.status_code == 200:
        sha = r.json()["sha"]

    content = base64.b64encode(
        json.dumps(history, ensure_ascii=False).encode()
    ).decode()

    data = {
        "message": "update weather data",
        "content": content,
        "branch": "main"
    }

    if sha:
        data["sha"] = sha

    requests.put(url, json=data, headers=headers)


# ---------------- 30 MIN CHECK ----------------
def can_save():
    if not os.path.exists(LAST_SAVE_FILE):
        return True

    try:
        with open(LAST_SAVE_FILE, "r", encoding="utf-8") as f:
            last = json.load(f).get("time", 0)

        now = datetime.now(BAKU_TZ).timestamp()
        return (now - last) >= 1800  # 30 минут

    except:
        return True


def update_last_save():
    data = {
        "time": datetime.now(BAKU_TZ).timestamp()
    }

    with open(LAST_SAVE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)


# ---------------- UPDATE ----------------
@app.route("/update", methods=["POST"])
def update():
    try:
        if not can_save():
            return jsonify({"ok": True, "skipped": True})

        data = request.get_json(force=True)
        if not data:
            return jsonify({"error": "No JSON"}), 400

        # ---- LOAD HISTORY ----
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, encoding="utf-8") as f:
                history = json.load(f)
                if not isinstance(history, list):
                    history = []
        else:
            history = []

        # ---- NEW POINT ----
        point = {
            "timestamp": datetime.now(BAKU_TZ).isoformat(),
            "time": datetime.now(BAKU_TZ).strftime("%d.%m %H:%M:%S"),

            "temp": float(data.get("temp") or 0),
            "wind": float(data.get("wind_ms") or 0),
            "gust": float(data.get("wind_gust_ms") or 0),
            "humidity": float(data.get("humidity") or 0),
            "pressure": float(data.get("pressure") or 0),
            "rain": float(data.get("rain_1h") or 0)
        }

        history.append(point)
        history = history[-2000:]

        # ---- SAVE LOCAL ----
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)

        # ---- SAVE TIMER ----
        update_last_save()

        # ---- PUSH TO GITHUB ----
        update_github(history)

        return jsonify({"ok": True, "saved": True})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------- HISTORY ----------------
@app.route("/history")
def history():
    if not os.path.exists(HISTORY_FILE):
        return jsonify([])

    with open(HISTORY_FILE, encoding="utf-8") as f:
        data = json.load(f)

    return jsonify(data if isinstance(data, list) else [])


@app.route("/history_flat")
def history_flat():
    if not os.path.exists(HISTORY_FILE):
        return jsonify([])

    with open(HISTORY_FILE, encoding="utf-8") as f:
        data = json.load(f)

    return jsonify(data if isinstance(data, list) else [])


# ---------------- STATION ----------------
@app.route("/station")
def station():
    if not os.path.exists(DATA_FILE):
        return jsonify({
            "temp": 0,
            "humidity": 0,
            "wind_ms": 0,
            "wind_gust_ms": 0,
            "pressure": 0,
            "rain_1h": 0,
            "rain_24h": 0
        })

    with open(DATA_FILE, encoding="utf-8") as f:
        return jsonify(json.load(f))


# ---------------- STATUS ----------------
@app.route("/status")
def status():
    if not os.path.exists(DATA_FILE):
        return jsonify({"status": "offline"})

    last = os.path.getmtime(DATA_FILE)
    now = datetime.now(BAKU_TZ).timestamp()

    if now - last > 300:
        return jsonify({"status": "offline"})

    return jsonify({"status": "online"})


# ---------------- RUN ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
