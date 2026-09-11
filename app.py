from flask import Flask, request, jsonify, send_from_directory
import json
import requests
import os
import hashlib
import sqlite3
import threading
from datetime import datetime
from zoneinfo import ZoneInfo
import base64
from html import escape


def update_github(history):
    """Writes history only to the data branch and reports GitHub errors."""
    if not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_TOKEN is not configured in Render")

    url = f"https://api.github.com/repos/{REPO}/contents/{FILE}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    existing = requests.get(url, headers=headers, params={"ref": HISTORY_BRANCH}, timeout=15)
    sha = None
    if existing.status_code == 200:
        sha = existing.json()["sha"]
    elif existing.status_code != 404:
        existing.raise_for_status()

    content = base64.b64encode(
        json.dumps(history, ensure_ascii=False, indent=2, sort_keys=True).encode()
    ).decode()
    payload = {"message": "update weather history", "content": content, "branch": HISTORY_BRANCH}
    if sha:
        payload["sha"] = sha

    saved = requests.put(url, json=payload, headers=headers, timeout=15)
    saved.raise_for_status()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO = "Meta-Baki/meta_baki_az"
FILE = "history.json"
HISTORY_BRANCH = "history-data"

BAKU_TZ = ZoneInfo("Asia/Baku")

# вњ”пёЏ Р’РђР–РќРћР• РРЎРџР РђР’Р›Р•РќРР• (РЎРўРђРўРРљРђ)
app = Flask(__name__, static_folder=".", static_url_path="")


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
LAST_SAVE_FILE = "last_save.json"

PUBLIC_SITE_URL = "https://meta-baki1.onrender.com"
STATION_NAME = "META Abşeron Proqnozu"
STATION_LOCATION = "Əhmədli, Bakı"


# ---------------- PAGE VIEW COUNTERS ----------------
# Set PAGE_VIEWS_DB to a path on a persistent Render Disk in production.
PAGE_VIEWS_DB = os.getenv("PAGE_VIEWS_DB", os.path.join(app.root_path, "page_views.sqlite3"))
PAGE_VIEW_LOCK = threading.Lock()
PAGE_VIEW_SECTIONS = {
    "monthlyForecastSection": ["story/Ay ərzində hava"],
    "metaSection": ["story/meta"],
    "historySection": ["story/history.txt", "story/image.jpg", "story/image.png"],
    "spaceSection": ["story/space"],
    "aboutSection": ["story/sayt haqqında/haqqımızda.txt"],
    "meteorologySection": ["story/sayt haqqında/meteorologiya.txt"],
    "systemSection": ["story/sayt haqqında/system.txt"],
}
# To manually set a counter, write its number here and increase the revision.
# Example: {"metaSection": 1250}. The value is applied once after deployment.
PAGE_VIEW_MANUAL_REVISION = 2
PAGE_VIEW_MANUAL_COUNTS = {
    "monthlyForecastSection": 537,  # Ay ərzində hava proqnozu
    "metaSection": 160,            # META xəbərlər
    "historySection": 283,          # Hava xəbərləri
    "spaceSection": 183,            # Günəş və kosmos
    "aboutSection": 1941,             # Haqqımızda
    "meteorologySection": 1354,      # Meteorologiya
    "systemSection": 1296,            # Sistem və sensorların vəziyyəti
}


def _page_content_version(section_id):
    """Hash the published files so an edited news item starts a fresh counter."""
    digest = hashlib.sha256()
    for relative_path in PAGE_VIEW_SECTIONS[section_id]:
        path = os.path.join(app.root_path, relative_path)
        if os.path.isdir(path):
            files = []
            for directory, _, filenames in os.walk(path):
                files.extend(os.path.join(directory, filename) for filename in filenames)
        else:
            files = [path]
        for file_path in sorted(files):
            digest.update(os.path.relpath(file_path, app.root_path).encode("utf-8"))
            try:
                with open(file_path, "rb") as source:
                    digest.update(source.read())
            except OSError:
                digest.update(b"missing")
    return digest.hexdigest()


def _page_views_connection():
    connection = sqlite3.connect(PAGE_VIEWS_DB, timeout=10)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS page_views (
            section_id TEXT PRIMARY KEY,
            views INTEGER NOT NULL DEFAULT 0,
            content_version TEXT NOT NULL
        )
    """)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(page_views)")}
    if "manual_revision" not in columns:
        connection.execute("ALTER TABLE page_views ADD COLUMN manual_revision INTEGER NOT NULL DEFAULT 0")
    return connection


@app.route("/api/page-views/<section_id>", methods=["GET", "POST"])
def page_views(section_id):
    if section_id not in PAGE_VIEW_SECTIONS:
        return jsonify({"error": "Unknown page section"}), 404

    # Reset on the server, before returning the shared total, whenever the
    # related news/text/image files have changed.
    version = _page_content_version(section_id)
    with PAGE_VIEW_LOCK:
        connection = _page_views_connection()
        try:
            row = connection.execute(
                "SELECT views, content_version, manual_revision FROM page_views WHERE section_id = ?", (section_id,)
            ).fetchone()
            if row is None:
                views = 0
                manual_revision = 0
                connection.execute(
                    "INSERT INTO page_views (section_id, views, content_version, manual_revision) VALUES (?, ?, ?, ?)",
                    (section_id, views, version, 0),
                )
            else:
                views, stored_version, manual_revision = row
                if stored_version != version:
                    views = 0
                    connection.execute(
                        "UPDATE page_views SET views = ?, content_version = ? WHERE section_id = ?",
                        (views, version, section_id),
                    )
            if section_id in PAGE_VIEW_MANUAL_COUNTS and manual_revision != PAGE_VIEW_MANUAL_REVISION:
                views = max(0, int(PAGE_VIEW_MANUAL_COUNTS[section_id]))
                connection.execute(
                    "UPDATE page_views SET views = ?, manual_revision = ? WHERE section_id = ?",
                    (views, PAGE_VIEW_MANUAL_REVISION, section_id),
                )
            if request.method == "POST":
                views += 1
                connection.execute("UPDATE page_views SET views = ? WHERE section_id = ?", (views, section_id))
            connection.commit()
            return jsonify({"section": section_id, "views": views})
        finally:
            connection.close()


def _number(value, default=0.0):
    """Return a finite-looking float without letting malformed station data break public pages."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _load_station_data():
    if not os.path.exists(DATA_FILE):
        return {}, None
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            data = json.load(f)
        updated = datetime.fromtimestamp(os.path.getmtime(DATA_FILE), BAKU_TZ)
        return data if isinstance(data, dict) else {}, updated
    except (OSError, json.JSONDecodeError):
        return {}, None


def _direction_name(degrees, language="az"):
    names = {
        "az": ["Ş", "ŞŞ-Ş", "Ş-Ş", "ŞŞ-C", "C", "CC-Q", "C-Q", "QQ-Ş"],
        "ru": ["С", "ССВ", "СВ", "ВЮВ", "Ю", "ЮЗ", "З", "СЗ"],
    }
    points = names.get(language, names["az"])
    return points[int((_number(degrees) + 22.5) // 45) % 8]


def _public_weather():
    data, updated = _load_station_data()
    age = None if updated is None else max(0, int((datetime.now(BAKU_TZ) - updated).total_seconds()))
    direction = _number(data.get("wind_dir"))
    return {
        "station": STATION_NAME,
        "location": STATION_LOCATION,
        "observation_type": "automatic_weather_station",
        "temperature_c": round(_number(data.get("temp")), 1),
        "humidity_percent": round(_number(data.get("humidity")), 1),
        "pressure_hpa": round(_number(data.get("pressure")), 1),
        "wind_kmh": round(_number(data.get("wind_ms")) * 3.6, 1),
        "gust_kmh": round(_number(data.get("wind_gust_ms")) * 3.6, 1),
        "wind_direction_degrees": round(direction),
        "wind_direction_az": _direction_name(direction, "az"),
        "wind_direction_ru": _direction_name(direction, "ru"),
        "rain_1h_mm": round(_number(data.get("rain_1h")), 1),
        "rain_24h_mm": round(_number(data.get("rain_24h")), 1),
        "updated_at": updated.isoformat() if updated else None,
        "data_age_seconds": age,
        "status": "online" if age is not None and age <= 300 else "offline",
        "source": STATION_NAME,
        "source_url": PUBLIC_SITE_URL,
    }


# ---------------- HOME ----------------
MENU_INJECTION = r"""<style>
.top-menu{display:none!important}
.menu-toggle{position:fixed!important;top:145px!important;left:3px!important;z-index:999999!important;width:130px!important;height:58px!important;display:flex!important;align-items:center;justify-content:center;gap:9px!important;visibility:visible!important;opacity:1!important;border:2px solid rgba(255,255,255,.7)!important;border-radius:16px!important;background:linear-gradient(135deg,#0ea5e9,#0369a1)!important;color:#fff!important;font:700 21px Arial!important;cursor:pointer!important;box-shadow:0 8px 22px rgba(0,0,0,.4)!important}
.menu-backdrop{position:fixed;inset:0;z-index:999990;background:rgba(2,6,23,.72);opacity:0;visibility:hidden;transition:.25s}.drawer{position:fixed;z-index:999999;top:0;left:0;width:min(390px,88vw);height:100dvh;display:flex;flex-direction:column;overflow-y:auto;background:#fff;color:#334155;box-shadow:12px 0 35px rgba(0,0,0,.38);transform:translateX(-105%);transition:.28s;text-align:left}.drawer.open{transform:translateX(0)}.menu-backdrop.open{opacity:1;visibility:visible}body.menu-open{overflow:hidden}.drawer-header{display:flex;align-items:center;gap:14px;padding:22px 20px;border-bottom:1px solid #e2e8f0}.drawer-header img{width:62px;height:62px;object-fit:contain}.drawer-title{font:700 21px/1.25 Arial}.drawer-close{margin-left:auto;border:0;background:transparent;color:#64748b;font-size:32px;cursor:pointer}.drawer-nav{display:grid;gap:10px;padding:20px}.drawer-nav button{border:0;border-radius:14px;padding:13px 16px;background:#1e293b;color:#fff;font:15px Arial;text-align:left;cursor:pointer}.drawer-nav button:hover{background:#0ea5e9}.drawer-actions{margin-top:auto;padding:20px;display:grid;gap:12px;border-top:1px solid #e2e8f0}.drawer-action{border:0;background:transparent;color:#64748b;padding:12px 8px;font-size:17px;text-align:left;cursor:pointer}
</style>
<button class="menu-toggle" id="menuToggle" type="button" aria-label="Open menu">☰ <span>MENÜ</span></button>
<div class="menu-backdrop" id="menuBackdrop"></div>
<aside class="drawer" id="sideMenu" aria-hidden="true"><div class="drawer-header"><img src="static/888-logo.png" alt="META logo"><div class="drawer-title">META<br>Hidrometeorologiya Departamenti</div><button class="drawer-close" type="button">×</button></div><nav class="drawer-nav"><button type="button" data-section="homeSection">🏠 Ana səhifə</button><button type="button" data-section="forecast7">🌦 7 günlük proqnoz</button><button type="button" data-section="forecast14Section">📅 14 günlük proqnoz</button><button type="button" data-section="chartSection">📊 Qrafiklər</button><button type="button" data-section="mapSection">🗺 Xəritələr</button><button type="button" data-section="radarSection">🌧 Radar</button><button type="button" data-section="historySection">📢 Hava haqqında</button><button type="button" data-section="spaceSection">☀️ Günəş və kosmos</button><button type="button" data-section="metaSection">⚡ META xəbər</button><button type="button" data-section="recordsSection">🏆 Rekordlar</button><button type="button" data-section="helpSection">📰 Məlumat</button></nav><div class="drawer-actions"><button class="drawer-action" id="refreshPage" type="button">⟳&nbsp;&nbsp; Обновить</button><button class="drawer-action" id="closeMenu" type="button">⊗&nbsp;&nbsp; Выход</button></div></aside>
<script>(function(){const d=document.getElementById("sideMenu"),b=document.getElementById("menuBackdrop"),t=document.getElementById("menuToggle"),x=d.querySelector(".drawer-close");function c(){d.classList.remove("open");b.classList.remove("open");document.body.classList.remove("menu-open")}function o(){d.classList.add("open");b.classList.add("open");document.body.classList.add("menu-open")}t.onclick=o;x.onclick=c;b.onclick=c;document.getElementById("closeMenu").onclick=c;document.getElementById("refreshPage").onclick=function(){location.reload()};d.querySelectorAll("[data-section]").forEach(function(e){e.onclick=function(){openSection(e.dataset.section);c()}});document.addEventListener("keydown",function(e){if(e.key==="Escape")c()})}());</script>"""


@app.route("/")
def home():
    index_path = os.path.join(app.root_path, "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        page = f.read()

    if 'id="menuToggle"' not in page:
        page = page.replace("</body>", MENU_INJECTION + "</body>")

    return app.response_class(page, mimetype="text/html")



# ---------------- HISTORY STORAGE ----------------
_HISTORY_CACHE = None


def make_history_entry(entry):
    now = datetime.now(BAKU_TZ)
    return {
        "timestamp": now.isoformat(),
        "time": now.strftime("%d.%m %H:%M:%S"),
        "temp": float(entry.get("temp", 0)),
        "wind": round(float(entry.get("wind_ms", 0)) * 3.6, 1),
        "gust": round(float(entry.get("wind_gust_ms", 0)) * 3.6, 1),
        "humidity": float(entry.get("humidity", 0)),
        "pressure": float(entry.get("pressure", 0)),
        "rain": float(entry.get("rain_1h", 0))
    }


def normalise_history(data):
    normalised = []

    for item in data:
        if not isinstance(item, dict):
            continue

        # Old entries used ISO time in `time` instead of `timestamp`.
        timestamp = item.get("timestamp") or item.get("time")
        if not isinstance(timestamp, str) or "T" not in timestamp:
            continue

        try:
            point_time = datetime.fromisoformat(timestamp)
        except ValueError:
            continue

        normalised.append({
            "timestamp": timestamp,
            "time": item.get("time") if "T" not in str(item.get("time", "")) else point_time.strftime("%d.%m %H:%M:%S"),
            "temp": float(item.get("temp", 0)),
            "wind": float(item.get("wind", 0)),
            "gust": float(item.get("gust", 0)),
            "humidity": float(item.get("humidity", 0)),
            "pressure": float(item.get("pressure", 0)),
            "rain": float(item.get("rain", 0))
        })

    return normalised

def load_history():
    """Loads persistent graph points from the history-data branch."""
    global _HISTORY_CACHE

    if _HISTORY_CACHE is not None:
        return _HISTORY_CACHE.copy()

    data = []
    try:
        response = requests.get(
            f"https://raw.githubusercontent.com/{REPO}/{HISTORY_BRANCH}/{FILE}",
            timeout=15
        )
        if response.status_code == 200:
            candidate = response.json()
            if isinstance(candidate, list):
                data = candidate
    except Exception:
        pass

    _HISTORY_CACHE = normalise_history(data)[-2000:]
    return _HISTORY_CACHE.copy()


def last_history_timestamp():
    history = load_history()
    if not history:
        return None
    try:
        return datetime.fromisoformat(history[-1]["timestamp"])
    except (KeyError, TypeError, ValueError):
        return None

def save_history(entry):
    global _HISTORY_CACHE

    data = load_history()
    data.append(make_history_entry(entry))
    _HISTORY_CACHE = data[-2000:]

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(_HISTORY_CACHE, f, ensure_ascii=False, indent=2)

    update_github(_HISTORY_CACHE)


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


# ---------------- PUBLIC MEDIA API ----------------
@app.route("/api/v1/current")
def api_current():
    """Stable public endpoint for partners that want to render their own design."""
    response = jsonify(_public_weather())
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Cache-Control"] = "public, max-age=30"
    return response


def _widget_html(language):
    ru = language == "ru"
    text = {
        "title": "Погода в Баку — онлайн" if ru else "Bakıda hava — canlı",
        "live": "В ЭФИРЕ" if ru else "CANLI",
        "temp": "Температура" if ru else "Temperatur",
        "humidity": "Влажность" if ru else "Rütubət",
        "pressure": "Давление" if ru else "Təzyiq",
        "wind": "Ветер" if ru else "Külək",
        "gust": "Порывы" if ru else "Küləyin şiddəti",
        "rain": "Осадки за 1 час" if ru else "Yağıntı • 1 saat",
        "updated": "Обновлено" if ru else "Yenilənib",
        "source": "Источник данных" if ru else "Məlumat mənbəyi",
        "offline": "Данные временно недоступны" if ru else "Məlumat müvəqqəti əlçatan deyil",
    }
    lang_code = "ru" if ru else "az"
    speed_unit = "км/ч" if ru else "km/saat"
    return f'''<!doctype html>
<html lang="{lang_code}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{{box-sizing:border-box}}html,body{{margin:0;background:transparent;font-family:Arial,sans-serif;color:#eaf6ff}}.card{{min-height:250px;padding:18px;border-radius:20px;background:linear-gradient(145deg,#062744,#0b172c);border:1px solid #245475;box-shadow:0 12px 35px #0005}}.head{{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:15px}}h1{{font-size:20px;margin:0}}.live{{font-size:11px;font-weight:800;color:#9af7bd;background:#125434;padding:7px 9px;border-radius:999px}}.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:9px}}.item{{padding:11px;border-radius:13px;background:#ffffff0d;border:1px solid #ffffff12}}.item span{{display:block;color:#9fb8cb;font-size:11px;margin-bottom:5px}}.item strong{{font-size:17px}}.foot{{display:flex;justify-content:space-between;gap:12px;align-items:end;margin-top:14px;color:#9fb8cb;font-size:11px}}.foot a{{color:#75d5ff;font-weight:800;text-decoration:none;text-align:right}}#notice{{display:none;margin:10px 0;color:#ffd48a;font-size:12px}}@media(max-width:470px){{.grid{{grid-template-columns:repeat(2,1fr)}}.card{{border-radius:14px;padding:14px}}h1{{font-size:17px}}}}
</style></head><body><main class="card"><div class="head"><h1>🌤 {text['title']}</h1><span class="live">● {text['live']}</span></div><div id="notice">{text['offline']}</div><section class="grid">
<div class="item"><span>🌡 {text['temp']}</span><strong id="temp">—</strong></div><div class="item"><span>💧 {text['humidity']}</span><strong id="humidity">—</strong></div><div class="item"><span>🧭 {text['pressure']}</span><strong id="pressure">—</strong></div><div class="item"><span>💨 {text['wind']}</span><strong id="wind">—</strong></div><div class="item"><span>⚡ {text['gust']}</span><strong id="gust">—</strong></div><div class="item"><span>🌧 {text['rain']}</span><strong id="rain">—</strong></div>
</section><footer class="foot"><span>{text['updated']}: <b id="updated">—</b></span><a href="{PUBLIC_SITE_URL}" target="_blank" rel="noopener">{text['source']}:<br>{STATION_NAME}</a></footer></main>
<script>
const $=id=>document.getElementById(id);function val(n,d=1){{return Number(n).toFixed(d)}}async function refresh(){{try{{const r=await fetch('/api/v1/current',{{cache:'no-store'}});if(!r.ok)throw Error();const d=await r.json();$('temp').textContent=val(d.temperature_c)+' °C';$('humidity').textContent=val(d.humidity_percent,0)+' %';$('pressure').textContent=val(d.pressure_hpa)+' hPa';$('wind').textContent=val(d.wind_kmh)+' {speed_unit}';$('gust').textContent=val(d.gust_kmh)+' {speed_unit}';$('rain').textContent=val(d.rain_1h_mm)+' mm';const dir='{lang_code}'==='ru'?d.wind_direction_ru:d.wind_direction_az;$('wind').textContent+=' · '+dir;$('updated').textContent=d.updated_at?new Intl.DateTimeFormat('{lang_code}-' + ('{lang_code}'==='ru'?'RU':'AZ'),{{hour:'2-digit',minute:'2-digit',timeZone:'Asia/Baku'}}).format(new Date(d.updated_at)):'—';$('notice').style.display=d.status==='online'?'none':'block'}}catch(e){{$('notice').style.display='block'}}}}refresh();setInterval(refresh,60000);
</script></body></html>'''


@app.route("/widget/weather")
@app.route("/widget/weather/<language>")
def weather_widget(language="az"):
    language = "ru" if language.lower() == "ru" else "az"
    response = app.response_class(_widget_html(language), mimetype="text/html")
    response.headers["Cache-Control"] = "public, max-age=300"
    return response


@app.route("/media")
def media_page():
    iframe_code = escape(
        f'<iframe src="{PUBLIC_SITE_URL}/widget/weather/az" width="100%" '
        'height="270" style="border:0" loading="lazy" title="META canlı hava"></iframe>'
    )
    page = f'''<!doctype html><html lang="az"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Media üçün canlı hava | {STATION_NAME}</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#061524;color:#e8f5ff;font:16px/1.6 Arial,sans-serif}}main{{width:min(1040px,calc(100% - 28px));margin:32px auto}}.hero,.box{{padding:28px;border:1px solid #24445d;border-radius:22px;background:#0a2136;margin-bottom:18px}}h1{{font-size:clamp(30px,6vw,52px);line-height:1.1;margin:0 0 14px}}h2{{margin-top:0}}p{{color:#c4d8e7}}.badge{{display:inline-block;padding:7px 11px;border-radius:999px;background:#0d5b39;color:#b8ffd6;font-weight:800}}.cols{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}iframe{{width:100%;height:270px;border:0}}pre{{overflow:auto;padding:17px;border-radius:13px;background:#020b13;color:#9ee6ff;white-space:pre-wrap}}a{{color:#6fd5ff}}@media(max-width:760px){{.cols{{grid-template-columns:1fr}}.hero,.box{{padding:20px}}}}
</style></head><body><main><section class="hero"><span class="badge">PULSUZ İNTEQRASİYA</span><h1>Media üçün canlı meteoroloji məlumatlar</h1><p>{STATION_NAME} Bakıdakı avtomatik stansiyadan faktiki göstəriciləri media saytlarına təqdim edir. Vidcet hər dəqiqə yenilənir və texniki xidmət bizim tərəfimizdən həyata keçirilir.</p></section><div class="cols"><section class="box"><h2>Canlı nümunə</h2><iframe src="/widget/weather/az" title="Canlı hava vidceti"></iframe></section><section class="box"><h2>Nələr təqdim olunur?</h2><p>Temperatur, rütubət, atmosfer təzyiqi, küləyin sürəti və istiqaməti, küləyin şiddəti, 1 və 24 saatlıq yağıntı.</p><p><strong>Yenilənmə:</strong> hər 60 saniyə<br><strong>Mənbə:</strong> avtomatik meteoroloji stansiya<br><strong>İstifadə:</strong> mənbə göstərilməklə pulsuz</p></section></div><section class="box"><h2>Bir sətirlə quraşdırma</h2><pre><code>{iframe_code}</code></pre><p>Rus versiyası üçün ünvanın sonunda <code>/az</code> əvəzinə <code>/ru</code> yazılır.</p></section><section class="box"><h2>API</h2><p>Öz dizaynınızda istifadə etmək üçün: <a href="/api/v1/current">{PUBLIC_SITE_URL}/api/v1/current</a></p><p>Əməkdaşlıq üçün <a href="{PUBLIC_SITE_URL}">META Abşeron Proqnozu</a> saytının əlaqə bölməsindən istifadə edə bilərsiniz.</p></section></main></body></html>'''
    return app.response_class(page, mimetype="text/html")


# ---------------- HISTORY ----------------
@app.route("/history")
def history():
    return jsonify(load_history())


# ---------------- FLAT HISTORY ----------------
@app.route("/history_flat")
def history_flat():
    return jsonify(load_history())


# ---------------- 30 MIN CHECK ----------------
def can_save():
    # The last point is stored in GitHub, so this survives deploys and restarts.
    last = last_history_timestamp()
    if last is None:
        return True

    return (datetime.now(BAKU_TZ) - last).total_seconds() >= 1800

# ---------------- FORECAST 7 ----------------
@app.route("/forecast7")
def forecast7():

    try:

        # Общий бесплатный прогнозный API Open-Meteo.
        # Он используется и для 14-дневного прогноза на странице.
        url = "https://api.open-meteo.com/v1/forecast"

        params = {

            "latitude": 40.4093,
            "longitude": 49.8671,

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
                "temperature_2m,"
                "weather_code,"
                "relative_humidity_2m,"
                "wind_speed_10m,"
                "surface_pressure,"
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

                "time": raw["daily"]["time"],

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

                "time":
                    raw["hourly"]["time"],

                "temperature_2m":
                    raw["hourly"]["temperature_2m"],

                "weathercode":
                    raw["hourly"]["weather_code"],

                "relative_humidity_2m":
                    raw["hourly"]["relative_humidity_2m"],

                "wind_speed_10m":
                    raw["hourly"]["wind_speed_10m"],

                "surface_pressure":
                    raw["hourly"]["surface_pressure"],

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
        warnings.append("вљ пёЏ GГјclГј kГјlЙ™k gГ¶zlЙ™nilir")

    if d.get("humidity", 0) > 90:
        warnings.append("рџЊ« Duman ehtimalД± yГјksЙ™kdir")

    if d.get("rain_1h", 0) > 0:
        warnings.append("рџЊ§ YaДџД±Еџ mГјЕџahidЙ™ olunur")

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
        text = "HekayЙ™ tapД±lmadД±."

    image_path = "/story/image.jpg"

    if os.path.exists("story/image.png"):
        image_path = "/story/image.png"

    return jsonify({"text": text, "image": image_path})


@app.route("/space_content")
def space_content():

    folder = "story/space"
    news = []

    try:
        files = sorted(
            [f for f in os.listdir(folder) if f.endswith(".txt")]
        )

        for file in files:

            name = os.path.splitext(file)[0]

            image = None

            if os.path.exists(f"{folder}/{name}.jpg"):
                image = f"/story/space/{name}.jpg"
            elif os.path.exists(f"{folder}/{name}.png"):
                image = f"/story/space/{name}.png"

            with open(f"{folder}/{file}", "r", encoding="utf-8") as f:
                text = f.read()

            news.append({
                "text": text,
                "image": image
            })

    except:
        pass

    return jsonify(news)


@app.route("/records_content")
def records_content():

    base_dir = os.path.dirname(os.path.abspath(__file__))
    records_dir = os.path.join(base_dir, "story", "records")

    text_path = os.path.join(records_dir, "records.txt")
    jpg_path = os.path.join(records_dir, "records.jpg")
    png_path = os.path.join(records_dir, "records.png")

    # РўРµРєСЃС‚
    if os.path.isfile(text_path):
        try:
            with open(text_path, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception as e:
            text = f"РћС€РёР±РєР° С‡С‚РµРЅРёСЏ records.txt: {e}"
    else:
        text = "Rekord mЙ™lumatlarД± tapД±lmadД±."

    # РР·РѕР±СЂР°Р¶РµРЅРёРµ
    image_path = None

    if os.path.isfile(jpg_path):
        image_path = "/story/records/records.jpg"
    elif os.path.isfile(png_path):
        image_path = "/story/records/records.png"

    return jsonify({
        "text": text,
        "image": image_path
    })


@app.route("/meta_content")
def meta_content():

    folder = "story/meta"
    news = []

    try:
        files = sorted(
            [f for f in os.listdir(folder) if f.endswith(".txt")]
        )

        for file in files:

            name = os.path.splitext(file)[0]

            image = None

            if os.path.exists(f"{folder}/{name}.jpg"):
                image = f"/story/meta/{name}.jpg"
            elif os.path.exists(f"{folder}/{name}.png"):
                image = f"/story/meta/{name}.png"

            with open(f"{folder}/{file}", "r", encoding="utf-8") as f:
                text = f.read()

            news.append({
                "text": text,
                "image": image
            })

    except:
        pass

    return jsonify(news)


@app.route('/story/<path:filename>')
def story_files(filename):
    return send_from_directory('story', filename)


@app.route("/test")
def test():
    return {"status": "ok"}


@app.route("/robots.txt")
def robots():
    return app.response_class(
        """User-agent: *
Allow: /

Sitemap: https://meta-baki1.onrender.com/sitemap.xml
""",
        mimetype="text/plain"
    )


@app.route("/sitemap.xml")
def sitemap():
    return send_from_directory(".", "sitemap.xml")


# ---------------- RUN ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False) 
