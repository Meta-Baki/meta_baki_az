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


# ---------------- SAVE TIMER ----------------
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
    with open(LAST_SAVE_FILE, "w", encoding="utf-8") as f:
        json.dump({"time": datetime.now(BAKU_TZ).timestamp()}, f)


# ---------------- SAVE HISTORY ----------------
def save_history(entry):

    data = {}

    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, encoding="utf-8") as f:
                data = json.load(f)
        except:
            data = {}

    today = datetime.now(BAKU_TZ).strftime("%Y-%m-%d")

    if today not in data:
        data[today] = []

    data[today].append({

        "timestamp": datetime.now(BAKU_TZ).isoformat(),
        "time": datetime.now(BAKU_TZ).strftime("%d.%m %H:%M:%S"),

        "temp": float(entry.get("temp", 0)),
        "wind": round(float(entry.get("wind_ms", 0)) * 3.6, 1),
        "gust": round(float(entry.get("wind_gust_ms", 0)) * 3.6, 1),
        "humidity": float(entry.get("humidity", 0)),
        "pressure": float(entry.get("pressure", 0)),
        "rain": float(entry.get("rain_1h", 0))
    })

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ---------------- HOME ----------------
@app.route("/")
def home():
    return send_from_directory(".", "index.html")


# ---------------- MANIFEST ----------------
@app.route("/manifest.json")
def manifest():
    return send_from_directory(".", "manifest.json")


# ---------------- SW ----------------
@app.route("/sw.js")
def service_worker():
    return send_from_directory(".", "sw.js")


# ---------------- UPDATE ----------------
@app.route("/update", methods=["POST"])
def update():

    try:
        data = request.get_json(force=True)

        if not data:
            return {"error": "No JSON"}, 400

        # ---------------- SAVE LIVE DATA ----------------
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        # ---------------- HISTORY (30 MIN ONLY) ----------------
        if can_save():
            save_history(data)
            update_last_save()

            # ---- LOAD FULL HISTORY FOR GITHUB ----
            try:
                with open(HISTORY_FILE, encoding="utf-8") as f:
                    history = json.load(f)
            except:
                history = {}

            update_github(history)

        return {"ok": True}

    except Exception as e:
        return {"error": str(e)}, 500


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

    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            data = json.load(f)

        return jsonify(data)

    except Exception as e:
        return jsonify({"error": str(e)})


# ---------------- HISTORY ----------------
@app.route("/history")
def history():

    try:
        with open(HISTORY_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return jsonify(data)

    except:
        return jsonify({})


# ---------------- FLAT HISTORY ----------------
@app.route("/history_flat")
def history_flat():

    try:
        with open(HISTORY_FILE, encoding="utf-8") as f:
            data = json.load(f)

        flat = []

        if isinstance(data, dict):
            for day in data:
                for item in data[day]:
                    flat.append(item)

        return jsonify(flat)

    except:
        return jsonify([])


# ---------------- DEBUG ----------------
@app.route("/debug_history")
def debug_history():
    try:
        with open(HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"error": "no file"}


# ---------------- WARNING ----------------
@app.route("/warning")
def warning():

    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            d = json.load(f)

    except:
        return jsonify([])

    warnings = []

    if d.get("wind_ms", 0) * 3.6 > 40:
        warnings.append("⚠️ Güclü külək gözlənilir")

    if d.get("humidity", 0) > 90:
        warnings.append("🌫 Duman ehtimalı yüksəkdir")

    if d.get("rain_1h", 0) > 0:
        warnings.append("🌧 Yağış müşahidə olunur")

    return jsonify(warnings)


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


# ---------------- STORY ----------------
@app.route("/history_content")
def history_content():

    text = ""

    try:
        with open("story/history.txt", "r", encoding="utf-8") as f:
            text = f.read()
    except:
        text = "Hekayə tapılmadı."

    image_path = "/story/image.jpg"

    if os.path.exists("story/image.png"):
        image_path = "/story/image.png"

    return jsonify({
        "text": text,
        "image": image_path
    })


# ---------------- STORY FILES ----------------
@app.route('/story/<path:filename>')
def story_files(filename):
    return send_from_directory('story', filename)


@app.route("/test")
def test():
    return {"status": "ok"}


# ---------------- RUN ----------------
if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
