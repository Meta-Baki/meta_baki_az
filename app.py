from flask import Flask, request, jsonify, send_from_directory
import json
import requests
import os
from datetime import datetime
from zoneinfo import ZoneInfo
import base64

# ---------------- CONFIG ----------------
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO = "Meta-Baki/meta-weather"
FILE = "history.json"

BAKU_TZ = ZoneInfo("Asia/Baku")

app = Flask(__name__)

DATA_FILE = "data.json"
HISTORY_FILE = "history.json"
LAST_SAVE_FILE = "last_save.json"


# ---------------- GITHUB SAVE ----------------
def update_github(history):

    url = f"https://api.github.com/repos/{REPO}/contents/{FILE}"

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }

    r = requests.get(url, headers=headers)

    sha = None
    if r.status_code == 200:
        sha = r.json().get("sha")

    content = base64.b64encode(
        json.dumps(history, ensure_ascii=False).encode("utf-8")
    ).decode("utf-8")

    data = {
        "message": "update weather data",
        "content": content,
        "branch": "main"
    }

    if sha:
        data["sha"] = sha

    requests.put(url, json=data, headers=headers)


# ---------------- HOME ----------------
@app.route("/")
def home():
    return send_from_directory(".", "index.html")


@app.route("/manifest.json")
def manifest():
    return send_from_directory(".", "manifest.json")


@app.route("/sw.js")
def service_worker():
    return send_from_directory(".", "sw.js")


# ---------------- SAVE HISTORY ----------------
def save_history(entry):

    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, encoding="utf-8") as f:
                data = json.load(f)
        except:
            data = []
    else:
        data = []

    if not isinstance(data, list):
        data = []

    data.append({
        "timestamp": datetime.now(BAKU_TZ).isoformat(),
        "time": datetime.now(BAKU_TZ).strftime("%d.%m %H:%M:%S"),
        "temp": float(entry.get("temp", 0)),
        "wind": float(entry.get("wind_ms", 0)) * 3.6,
        "gust": float(entry.get("wind_gust_ms", 0)) * 3.6,
        "humidity": float(entry.get("humidity", 0)),
        "pressure": float(entry.get("pressure", 0)),
        "rain": float(entry.get("rain_1h", 0))
    })

    data = data[-2000:]

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ---------------- 30 MIN CHECK ----------------
def can_save():

    if not os.path.exists(LAST_SAVE_FILE):
        return True

    try:
        with open(LAST_SAVE_FILE, "r", encoding="utf-8") as f:
            last = json.load(f).get("time", 0)

        now = datetime.now(BAKU_TZ).timestamp()

        return (now - last) >= 1800

    except:
        return True


# ---------------- UPDATE ----------------
@app.route("/update", methods=["POST"])
def update():

    try:
        data = request.get_json(force=True)

        if not data:
            return {"error": "No JSON"}, 400

        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        if can_save():
            save_history(data)

            with open(LAST_SAVE_FILE, "w", encoding="utf-8") as f:
                json.dump({"time": datetime.now(BAKU_TZ).timestamp()}, f)

        # -------- LOAD FROM GITHUB SAFE --------
        history = []

        try:
            url = f"https://api.github.com/repos/{REPO}/contents/{FILE}"
            r = requests.get(url, timeout=10)

            if r.status_code == 200:
                content = r.json().get("content")

                if content:
                    history = json.loads(
                        base64.b64decode(content).decode("utf-8")
                    )

                if not isinstance(history, list):
                    history = []

        except:
            history = []

        history.append({
            "temp": data.get("temp"),
            "humidity": data.get("humidity"),
            "pressure": data.get("pressure"),
            "time": datetime.now(BAKU_TZ).isoformat()
        })

        history = history[-2000:]

        update_github(history)

        return {"ok": True}

    except Exception as e:
        return {"error": str(e)}, 500


# ---------------- STATION ----------------
@app.route("/station")
def station():

    if not os.path.exists(DATA_FILE):
        return jsonify({})

    with open(DATA_FILE, encoding="utf-8") as f:
        return jsonify(json.load(f))


# ---------------- HISTORY ----------------
@app.route("/history")
def history():

    if not os.path.exists(HISTORY_FILE):
        return jsonify([])

    try:
        with open(HISTORY_FILE, encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            flat = []
            for v in data.values():
                flat.extend(v)
            return jsonify(flat)

        return jsonify(data if isinstance(data, list) else [])

    except:
        return jsonify([])


# ---------------- HISTORY FLAT (FIXED) ----------------
@app.route("/history_flat")
def history_flat():

    try:
        url = f"https://api.github.com/repos/{REPO}/contents/{FILE}"
        r = requests.get(url, timeout=10)

        if r.status_code != 200:
            return jsonify([])

        content = r.json().get("content")

        if not content:
            return jsonify([])

        data = json.loads(
            base64.b64decode(content).decode("utf-8")
        )

        if isinstance(data, dict):
            flat = []
            for v in data.values():
                flat.extend(v)
            return jsonify(flat)

        return jsonify(data if isinstance(data, list) else [])

    except:
        return jsonify([])


# ---------------- RUN ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
