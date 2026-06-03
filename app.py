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


# ---------------- GITHUB ----------------
def update_github(history):
    url = f"https://api.github.com/repos/{REPO}/contents/{FILE}"

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }

    r = requests.get(url, headers=headers)
    sha = r.json()["sha"] if r.status_code == 200 else None

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


# ---------------- LOAD HISTORY ----------------
def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []

    try:
        with open(HISTORY_FILE, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except:
        return []


# ---------------- SAVE TIMER ----------------
def can_save_history():
    if not os.path.exists(LAST_SAVE_FILE):
        return True

    try:
        with open(LAST_SAVE_FILE, "r", encoding="utf-8") as f:
            last = json.load(f).get("time", 0)

        now = datetime.now(BAKU_TZ).timestamp()
        return (now - last) >= 1800  # 30 min
    except:
        return True


def update_last_save():
    with open(LAST_SAVE_FILE, "w", encoding="utf-8") as f:
        json.dump({"time": datetime.now(BAKU_TZ).timestamp()}, f)


# ---------------- UPDATE (СТАНЦИЯ) ----------------
@app.route("/update", methods=["POST"])
def update():
    try:
        data = request.get_json(force=True)
        if not data:
            return {"error": "No JSON"}, 400

        # ---- ВСЕГДА ОБНОВЛЯЕМ ТЕКУЩИЕ ДАННЫЕ ----
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)

        # ---- ЛОГ ДЛЯ ГРАФИКА (раз в 30 минут) ----
        if can_save_history():
            history = load_history()

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

            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2)

            update_last_save()
            update_github(history)

        return jsonify({"ok": True})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


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


# ---------------- HISTORY ----------------
@app.route("/history")
def history():
    return jsonify(load_history())


@app.route("/history_flat")
def history_flat():
    return jsonify(load_history())


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
