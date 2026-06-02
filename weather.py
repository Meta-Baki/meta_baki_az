import tinytuya
import requests
import time
import os
import json
from datetime import datetime
from colorama import init, Fore

init(autoreset=True)

# --- DEVICE ---
DEVICE_ID = "bff26141d68abf0be9jwr7"
IP = "192.168.100.191"
LOCAL_KEY = "Yp1G+gWm9.rW+54Y"
VERSION = 3.5

# --- WEATHER UNDERGROUND ---
WU_ID = "IBAKU35"
WU_PASSWORD = "POX2a9WI"

# --- RP5 ---
API_KEY_RP5 = "b42d217441d2150f7e9417a57da32728"

# --- WEATHERCLOUD ---
WC_ID = "583144e00e0834e2"
WC_KEY = "8fa375f4e63254ff84e8bb2c9639b2d3"

# --- PWS WEATHER ---
PWS_ID = "a3e7be3eae29be6fbf888k"
PWS_KEY = "b97caa97022cabfafb6cc6bd118324cb"

d = tinytuya.Device(DEVICE_ID, IP, LOCAL_KEY)
d.set_version(VERSION)

wind_dir_map = {
    "N": 0, "NE": 45, "E": 90, "SE": 135,
    "S": 180, "SW": 225, "W": 270, "NW": 315
}

desktop = os.path.join(os.path.expanduser("~"), "Desktop", "метеостанция")

if not os.path.exists(desktop):
    os.makedirs(desktop)

log_1min = os.path.join(desktop, "запись 1 минута.txt")
log_3h = os.path.join(desktop, "запись 3 часа.txt")

last_report_hour = None
report_hours = [23, 3, 6, 9, 12, 15, 18, 21]

hour_start_rain = None
last_hour = None


def convert_wind_to_mph(ms):
    return ms * 2.237 if ms else 0


def convert_pressure_to_inhg(hpa):
    return hpa * 0.02953 if hpa else 0


# =========================
# RP5
# =========================

def send_to_rp5(temp, hum, pressure, rain, wind_dir, wind_speed, wind_gust):
    try:
        requests.get("http://sgate.rp5.ru/", params={
            "T": temp,
            "U": hum,
            "P": pressure,
            "R": rain,
            "DD": wind_dir,
            "FF": wind_speed,
            "ff10": wind_gust,
            "updated": int(time.time()),
            "api_key": API_KEY_RP5
        }, timeout=10)

    except:
        pass


# =========================
# WEATHERCLOUD
# =========================

def send_to_weathercloud(temp, hum, pressure, wind_dir, wind_speed, wind_gust, rain):
    try:
        wind_kmh = wind_speed * 3.6 if wind_speed else 0
        gust_kmh = wind_gust * 3.6 if wind_gust else 0

        requests.get("http://api.weathercloud.net/v01/set", params={
            "wid": WC_ID,
            "key": WC_KEY,
            "temp": int(temp * 10),
            "hum": int(hum),
            "bar": int(pressure * 10),
            "winddir": int(wind_dir),
            "windspeed": int(wind_kmh * 10),
            "windgust": int(gust_kmh * 10),
            "rain": int(rain * 10)
        }, timeout=10)

    except:
        pass


# =========================
# PWS WEATHER
# =========================

def send_to_pws(temp, hum, pressure, wind_dir, wind_speed, wind_gust, rain):
    try:
        requests.get(
            "https://pwsupdate.pwsweather.com/api/v1/submitwx",
            params={
                "ID": PWS_ID,
                "PASSWORD": PWS_KEY,
                "tempf": temp * 9 / 5 + 32,
                "humidity": hum,
                "baromin": convert_pressure_to_inhg(pressure),
                "winddir": wind_dir,
                "windspeedmph": convert_wind_to_mph(wind_speed),
                "windgustmph": convert_wind_to_mph(wind_gust),
                "rainin": rain * 0.03937,
                "dateutc": "now"
            },
            timeout=10
        )

    except:
        pass


while True:
    try:
        data = d.status()
        dps = data.get("dps", {})

        temp_out = round((dps.get("103") or 0) / 10, 1)
        humidity_out = round((dps.get("104") or 0) / 10, 1)

        temp_in = round((dps.get("101") or 0) / 10, 1)
        humidity_in = round((dps.get("102") or 0) / 10, 1)

        pressure = round((dps.get("109") or 0) / 10, 1)

        wind_dir_raw = dps.get("112")

        wind_speed_kmh = dps.get("110") or 0
        wind_gust_kmh = dps.get("111") or 0

        wind_speed = round(wind_speed_kmh / 3.6, 2)
        wind_gust = round(wind_gust_kmh / 3.6, 2)

        # =========================
        # 🌧 ОСАДКИ
        # =========================

        rain_raw = dps.get("114") or 0

        # Значение прямо с метеостанции
        rain_total = round(rain_raw / 100, 1)

        now_dt = datetime.now()
        current_hour = now_dt.hour
        today = now_dt.strftime("%Y-%m-%d")

        # =========================
        # 24 ЧАСА
        # =========================

        # При запуске программы
        if "saved_day" not in globals():
            saved_day = today
            rain_start_day = rain_total

        # В 00:00 сохраняем новое стартовое значение
        if today != saved_day:
            saved_day = today
            rain_start_day = rain_total

        # Осадки за сутки
        rain_24h = round(rain_total - rain_start_day, 1)

        # Защита от отрицательных значений
        if rain_24h < 0:
            rain_start_day = rain_total
            rain_24h = 0.0

        # Если сама станция показывает 0.0 — тоже 0.0
        if rain_total == 0:
            rain_24h = 0.0
            rain_start_day = 0.0

        # =========================
        # 1 ЧАС
        # =========================

        if "hour_start_rain" not in globals():
            hour_start_rain = rain_total

        if "last_hour" not in globals():
            last_hour = current_hour

        # Каждый новый час
        if current_hour != last_hour:
            hour_start_rain = rain_total
            last_hour = current_hour

        rain_1h = round(rain_total - hour_start_rain, 1)

        if rain_1h < 0:
            hour_start_rain = rain_total
            rain_1h = 0.0

        # Если станция 0.0
        if rain_total == 0:
            rain_1h = 0.0
            hour_start_rain = 0.0

        wind_dir = wind_dir_map.get(str(wind_dir_raw), 0)

        now = now_dt.strftime("%d.%m.%Y %H:%M:%S")

        # =========================
        # CMD
        # =========================

        print("\n" + Fore.WHITE + "========================")
        print(Fore.LIGHTBLACK_EX + f"Time: {now}")

        print(Fore.WHITE + "----- INDOOR -----")
        print(Fore.CYAN + f"Temp: {temp_in} *C")
        print(Fore.CYAN + f"Humidity: {humidity_in} %")

        print(Fore.WHITE + "----- OUTDOOR -----")
        print(Fore.GREEN + f"Temp: {temp_out} *C")
        print(Fore.GREEN + f"Humidity: {humidity_out} %")

        print(Fore.WHITE + "----- DATA -----")
        print(Fore.YELLOW + f"Pressure: {pressure} hPa")
        print(Fore.YELLOW + f"Dir: {wind_dir}° Wind: {wind_speed_kmh} km/h Gust: {wind_gust_kmh} km/h")
        print(Fore.YELLOW + f"Rain 1h: {rain_1h:.1f} mm | Rain 24h: {rain_24h:.1f} mm")

        print(Fore.WHITE + "----- PROGRAM -----")
        print(Fore.RED + "WU data sent")
        print(Fore.RED + "RP5 data sent")
        print(Fore.RED + "WeatherCloud data sent")
        print(Fore.RED + "PWS data sent")

        # НЕ сохранять пустые данные
        if (
            temp_out == 0 and
            humidity_out == 0 and
            pressure == 0 and
            wind_speed_kmh == 0 and
            wind_gust_kmh == 0
        ):
            print(Fore.RED + "EMPTY DATA SKIPPED")
            time.sleep(60)
            continue

        log_line = (
            f"|{now:<19}| "
            f"IN:TEMP:{temp_in:5.1f}*C RH:{humidity_in:5.1f}% | "
            f"OUT:TEMP:{temp_out:5.1f}*C RH:{humidity_out:5.1f}% | "
            f"BARO:{pressure:7.1f} hPa | "
            f"DIR:{wind_dir:3d}° SPEED:{wind_speed_kmh:3d}km/h | "
            f"GUST:{wind_gust_kmh:3d}km/h | "
            f"RAIN 1h:{rain_1h:4.1f} mm | 24h:{rain_24h:4.1f} mm|\n"
        )

        with open(log_1min, "a", encoding="utf-8") as f:
            f.write(log_line)

        if current_hour in report_hours and last_report_hour != current_hour:
            with open(log_3h, "a", encoding="utf-8") as f:
                f.write("\n=== ОТЧЁТ ===\n")
                f.write(log_line)
            last_report_hour = current_hour

        try:
            requests.post("http://127.0.0.1:5000/update", json={
                "temp": temp_out,
                "humidity": humidity_out,
                "pressure": pressure,
                "wind_ms": wind_speed,
                "wind_gust_ms": wind_gust,
                "wind_dir": wind_dir,
                "rain_1h": rain_1h,
                "rain_24h": rain_24h
            }, timeout=5)
        except:
            pass

        # =========================
        # SEND
        # =========================

        send_to_rp5(
            temp_out,
            humidity_out,
            pressure,
            rain_24h,
            wind_dir,
            wind_speed,
            wind_gust
        )

        send_to_weathercloud(
            temp_out,
            humidity_out,
            pressure,
            wind_dir,
            wind_speed,
            wind_gust,
            rain_24h
        )

        send_to_pws(
            temp_out,
            humidity_out,
            pressure,
            wind_dir,
            wind_speed,
            wind_gust,
            rain_24h
        )

    except Exception as e:
        print(Fore.RED + f"ERROR: {e}")

    time.sleep(60)