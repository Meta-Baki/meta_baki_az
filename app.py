from flask import Flask, request, jsonify, send_from_directory
import json
import requests
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import base64

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

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO = "Meta-Baki/meta-weather"
FILE = "history.json"

BAKU_TZ = ZoneInfo("Asia/Baku")

app = Flask(__name__)


# ---------------- MANIFEST ----------------
@app.route("/manifest.json")
def manifest():
    return send_from_directory(".", "manifest.json")


# ---------------- SERVICE WORKER ----------------
@app.route("/sw.js")
def service_worker():
    return send_from_directory(".", "sw.js")

DATA_FILE = "data.json"
HISTORY_FILE = "history.json"

# ДОБАВЛЕНО: контроль 30 минут
LAST_SAVE_FILE = "last_save.json"


# ---------------- HOME ----------------
@app.route("/")
def home():
    return send_from_directory(".", "index.html")


# ---------------- 30 MIN CHECK ----------------
def can_save():

    if not os.path.exists(LAST_SAVE_FILE):
        return True

    try:
        with open(LAST_SAVE_FILE, "r", encoding="utf-8") as f:
            last = json.load(f).get("time")

        if not last:
            return True

        last_time = datetime.fromisoformat(last)
        now = datetime.now(BAKU_TZ)

        return (now - last_time).total_seconds() >= 1800

    except:
        return True


# ---------------- UPDATE ----------------
@app.route("/update", methods=["POST"])
def update():
    try:
        data = request.get_json(force=True)

        if not data:
            return {"error": "No JSON"}, 400

        # =========================
        # ⏱ 30 МИНУТ ЗАЩИТА
        # =========================
        if os.path.exists(LAST_SAVE_FILE):
            with open(LAST_SAVE_FILE, "r", encoding="utf-8") as f:
                last = json.load(f).get("time")
        else:
            last = None

        if last:
            last_time = datetime.fromisoformat(last)

            # если время без timezone — фиксируем
            if last_time.tzinfo is None:
                last_time = last_time.replace(tzinfo=BAKU_TZ)

            now = datetime.now(BAKU_TZ)

            if (now - last_time).total_seconds() < 1800:
                return {"ok": True, "skipped": True}

        # =========================
        # 📅 СБРОС В 00:00
        # =========================
        today = datetime.now(BAKU_TZ).strftime("%Y-%m-%d")

        if os.path.exists("last_day.json"):
            with open("last_day.json", "r", encoding="utf-8") as f:
                last_day = json.load(f).get("day")
        else:
            last_day = None

        if last_day != today:
            history = []
        else:
            if os.path.exists(HISTORY_FILE):
                with open(HISTORY_FILE, encoding="utf-8") as f:
                    try:
                        history = json.load(f)
                        if not isinstance(history, list):
                            history = []
                    except:
                        history = []
            else:
                history = []

        with open("last_day.json", "w", encoding="utf-8") as f:
            json.dump({"day": today}, f)

        # =========================
        # 📊 ДОБАВЛЕНИЕ ДАННЫХ
        # =========================
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

        # =========================
        # 💾 СОХРАНЕНИЕ
        # =========================
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)

        # =========================
        # ☁️ GITHUB UPDATE
        # =========================
        update_github(history)

        # сохраняем время последней записи
        with open(LAST_SAVE_FILE, "w", encoding="utf-8") as f:
            json.dump({"time": datetime.now(BAKU_TZ).isoformat()}, f)

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
        if not os.path.exists(HISTORY_FILE):
            return jsonify([])

        with open(HISTORY_FILE, encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            return jsonify([])

        # фильтр NaN защита
        clean = [
            x for x in data
            if isinstance(x, dict) and "temp" in x and "time" in x
        ]

        return jsonify(clean)

    except:
        return jsonify([])


# ---------------- DEBUG ENDPOINT ----------------
@app.route("/debug_history")
def debug_history():
    try:
        with open(HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"error": "no file"}


# ---------------- FLAT HISTORY ----------------
@app.route("/history_flat")
def history_flat():
    try:
        if not os.path.exists(HISTORY_FILE):
            return jsonify([])

        with open(HISTORY_FILE, encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            return jsonify([])

        return jsonify(data)

    except:
        return jsonify([])


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

        # нормальное время
        "timestamp": datetime.now(BAKU_TZ).isoformat(),

        # красивое время
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


# ---------------- FORECAST 7 ----------------
@app.route("/forecast7")
def forecast7():

    try:

        url = "https://api.open-meteo.com/v1/ecmwf"

        params = {

            "latitude": 40.379228,
            "longitude": 49.9625323,

            "daily":
                "weather_code,"
                "temperature_2m_max,"
                "temperature_2m_min,"
                "apparent_temperature_max,"
                "apparent_temperature_min,"
                "precipitation_probability_max,"
                "wind_speed_10m_mean,"
                "cloud_cover_mean,"
                "uv_index_max,"
                "sunrise,"
                "sunset,"
                "wind_speed_10m_max,"
                "wind_direction_10m_dominant,"
                "wind_gusts_10m_max,"
                "surface_pressure_mean,"
                "precipitation_sum",

            "hourly":
                "dew_point_2m,"
                "visibility",

            "forecast_days": 7,

            "timezone": "Asia/Baku"
        }

        r = requests.get(url, params=params, timeout=20)

        if r.status_code != 200:
            return jsonify({
                "error": "ECMWF API error",
                "status": r.status_code,
                "response": r.text
            })

        raw = r.json()

        if "daily" not in raw:
            return jsonify({
                "error": "No daily data",
                "response": raw
            })

        data = {

            "daily": {

                "time":
                    raw["daily"]["time"],

                "weathercode":
                    raw["daily"]["weather_code"],

                "temperature_2m_max":
                    raw["daily"]["temperature_2m_max"],

                "temperature_2m_min":
                    raw["daily"]["temperature_2m_min"],

                "apparent_temperature_max":
                    raw["daily"]["apparent_temperature_max"],

                "apparent_temperature_min":
                    raw["daily"]["apparent_temperature_min"],

                "precipitation_probability_max":
                    raw["daily"]["precipitation_probability_max"],

                "wind_speed_10m_mean":
                    raw["daily"]["wind_speed_10m_mean"],

                "cloud_cover_mean":
                    raw["daily"]["cloud_cover_mean"],

                "uv_index_max":
                    raw["daily"]["uv_index_max"],

                "sunrise":
                    raw["daily"]["sunrise"],

                "sunset":
                    raw["daily"]["sunset"],

                "precipitation_sum":
                    raw["daily"]["precipitation_sum"],

                "windspeed_10m_max":
                    raw["daily"]["wind_speed_10m_max"],

                "winddirection_10m_dominant":
                    raw["daily"]["wind_direction_10m_dominant"],

                "windgusts_10m_max":
                    raw["daily"]["wind_gusts_10m_max"],

                "surface_pressure_mean":
                    raw["daily"]["surface_pressure_mean"]
            },

            "hourly": {

                "dew_point_2m":
                    raw["hourly"]["dew_point_2m"],

                "visibility":
                    raw["hourly"]["visibility"]
            }
        }

        return jsonify(data)

    except Exception as e:
        return jsonify({"error": str(e)})


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


# ---------------- STORY CONTENT ----------------
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
