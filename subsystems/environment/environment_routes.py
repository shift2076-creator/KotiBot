from __future__ import annotations

import json
import math
import os
import urllib.request
from pathlib import Path
from threading import Event, Lock
from urllib.parse import urlsplit

from flask import jsonify, request

from server_core.io import json_exists, read_json, write_json_atomic

NOAA_SOURCE = "noaa"
AIRNOW_AQI_SOURCE = "airnow"
NOAA_LABEL = "NOAA weather.gov"
AIRNOW_AQI_LABEL = "AirNow observations"
AIRNOW_REPORTING_AREA_URL = "https://files.airnowtech.org/airnow/today/reportingarea.dat"
ZIP_LOOKUP_LABEL = "Zippopotam.us ZIP lookup"
NOAA_STATION_LABEL = "NOAA observation station"
MATTER_LABEL = "Matter sensors"
DEFAULT_REFRESH_SECONDS = 900

ALLOWED_REMOTE_HOSTS = {
    "api.weather.gov",
    "api.zippopotam.us",
    "files.airnowtech.org",
}


def validated_remote_url(url):
    url = str(url or "").strip()
    parsed = urlsplit(url)

    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or parsed.hostname not in ALLOWED_REMOTE_HOSTS
    ):
        raise ValueError("remote URL is not allowlisted")

    return url


class AllowlistedRedirectHandler(
    urllib.request.HTTPRedirectHandler
):
    def redirect_request(
        self,
        req,
        fp,
        code,
        msg,
        headers,
        newurl,
    ):
        validated_remote_url(newurl)

        return super().redirect_request(
            req,
            fp,
            code,
            msg,
            headers,
            newurl,
        )


REMOTE_OPENER = urllib.request.build_opener(
    AllowlistedRedirectHandler()
)

def register_environment_routes(app, context):
    state_file = Path(context["state_file"])
    matter_state_file = Path(context["matter_state_file"])
    clients = context.get("clients", {})
    state_lock = context.get("state_lock")
    now_epoch = context["now_epoch"]
    broadcast_state = context.get("broadcast_state")
    stop_event = context.get("environment_stop") or Event()
    lock = Lock()

    def default_state():
        return {
            "settings": {
                "zip_code": "",
                "weather_source": NOAA_SOURCE,
                "air_quality_source": "none",
                "refresh_seconds": DEFAULT_REFRESH_SECONDS,
            },
            "weather_cache": {},
        }

    def clean_zip(value):
        return "".join(ch for ch in str(value or "") if ch.isdigit())[:5]

    def clean_refresh(value):
        try:
            return min(3600, max(300, int(value)))
        except Exception:
            return DEFAULT_REFRESH_SECONDS

    def clean_settings(value):
        data = value if isinstance(value, dict) else {}
        weather_source = str(data.get("weather_source") or data.get("weatherSource") or NOAA_SOURCE).strip().lower()
        air_quality_source = str(data.get("air_quality_source") or data.get("airQualitySource") or "none").strip().lower()

        if air_quality_source == "openmeteo":
            air_quality_source = AIRNOW_AQI_SOURCE
        elif air_quality_source not in ("none", AIRNOW_AQI_SOURCE):
            air_quality_source = "none"

        return {
            "zip_code": clean_zip(data.get("zip_code") or data.get("zipCode")),
            "weather_source": NOAA_SOURCE if weather_source in ("", "nws", "weather.gov", NOAA_SOURCE) else NOAA_SOURCE,
            "air_quality_source": air_quality_source,
            "refresh_seconds": clean_refresh(data.get("refresh_seconds") or data.get("refreshSeconds") or DEFAULT_REFRESH_SECONDS),
        }

    def read_state_unlocked():
        state = default_state()

        try:
            data = read_json(state_file)
        except FileNotFoundError:
            return state
        except Exception:
            app.logger.exception("Environment state could not be read")
            return state

        if isinstance(data, dict):
            if isinstance(data.get("settings"), dict):
                state["settings"].update(data["settings"])
            if isinstance(data.get("weather_cache"), dict):
                state["weather_cache"] = data["weather_cache"]

        state["settings"] = clean_settings(state.get("settings"))
        return state

    def write_state_unlocked(state):
        state = state if isinstance(state, dict) else default_state()
        state["settings"] = clean_settings(state.get("settings"))
        state["weather_cache"] = state.get("weather_cache") if isinstance(state.get("weather_cache"), dict) else {}
        write_json_atomic(state_file, state)

    def ensure_state_file():
        if json_exists(state_file):
            return

        write_state_unlocked(default_state())

    ensure_state_file()

    def fetch_json(url, timeout=8):
        user_agent = os.environ.get("KOTIBOT_NOAA_USER_AGENT", "KotiBot/1.0")
        req = urllib.request.Request(
            validated_remote_url(url),
            headers={
                "Accept": "application/geo+json, application/json",
                "User-Agent": user_agent,
            },
        )

        with REMOTE_OPENER.open(req, timeout=timeout) as response:
            validated_remote_url(response.geturl())
            return json.loads(response.read().decode("utf-8"))

    def fetch_text(url, timeout=8):
        user_agent = os.environ.get("KOTIBOT_NOAA_USER_AGENT", "KotiBot/1.0")
        req = urllib.request.Request(
            validated_remote_url(url),
            headers={
                "Accept": "text/plain",
                "User-Agent": user_agent,
            },
        )

        with REMOTE_OPENER.open(req, timeout=timeout) as response:
            validated_remote_url(response.geturl())
            return response.read().decode("utf-8-sig", errors="replace")

    def zip_to_point(zip_code):
        data = fetch_json(f"https://api.zippopotam.us/us/{zip_code}")
        places = data.get("places") if isinstance(data, dict) else []
        place = places[0] if isinstance(places, list) and places and isinstance(places[0], dict) else None

        if not place:
            raise RuntimeError("ZIP code lookup returned no location")

        return {
            "latitude": float(place.get("latitude")),
            "longitude": float(place.get("longitude")),
            "city": str(place.get("place name") or ""),
            "state": str(place.get("state abbreviation") or place.get("state") or ""),
        }

    def distance_miles(lat1, lon1, lat2, lon2):
        radius_miles = 3958.8
        lat1 = math.radians(float(lat1))
        lon1 = math.radians(float(lon1))
        lat2 = math.radians(float(lat2))
        lon2 = math.radians(float(lon2))
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        return radius_miles * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def noaa_station_id(station):
        properties = station.get("properties") if isinstance(station, dict) else {}
        identifier = str(properties.get("stationIdentifier") or properties.get("station_id") or "").strip()

        if identifier:
            return identifier

        station_url = str(station.get("id") or properties.get("@id") or "").rstrip("/")
        return station_url.split("/")[-1] if station_url else ""

    def noaa_station_url(station):
        properties = station.get("properties") if isinstance(station, dict) else {}
        station_url = str(station.get("id") or properties.get("@id") or "").rstrip("/")

        if station_url:
            return station_url

        station_id = noaa_station_id(station)
        return f"https://api.weather.gov/stations/{station_id}" if station_id else ""

    def station_summary(station, point):
        properties = station.get("properties") if isinstance(station, dict) else {}
        geometry = station.get("geometry") if isinstance(station, dict) else {}
        coordinates = geometry.get("coordinates") if isinstance(geometry, dict) else []
        station_lat = None
        station_lon = None

        if isinstance(coordinates, list) and len(coordinates) >= 2:
            station_lon = coordinates[0]
            station_lat = coordinates[1]

        miles = None
        if station_lat is not None and station_lon is not None:
            miles = round(distance_miles(point["latitude"], point["longitude"], station_lat, station_lon), 1)

        return {
            "id": noaa_station_id(station),
            "name": str(properties.get("name") or ""),
            "url": noaa_station_url(station),
            "latitude": station_lat,
            "longitude": station_lon,
            "distance_miles": miles,
        }

    def sorted_stations(stations, point):
        summaries = [station_summary(station, point) for station in stations if isinstance(station, dict)]
        summaries = [station for station in summaries if station.get("id") and station.get("url")]
        return sorted(summaries, key=lambda station: station.get("distance_miles") if station.get("distance_miles") is not None else 999999)

    def noaa_value(properties, key):
        value = properties.get(key) if isinstance(properties, dict) else None

        if isinstance(value, dict):
            value = value.get("value")

        return safe_float(value)

    def c_to_f(value):
        value = safe_float(value)
        return None if value is None else round((value * 9 / 5) + 32, 1)

    def current_observation_from_station(station):
        station_url = str(station.get("url") or "").rstrip("/")

        if not station_url:
            return None

        data = fetch_json(f"{station_url}/observations/latest")
        properties = data.get("properties") if isinstance(data, dict) else {}
        temperature_f = c_to_f(noaa_value(properties, "temperature"))

        if temperature_f is None:
            return None

        humidity = noaa_value(properties, "relativeHumidity")
        condition = str(properties.get("textDescription") or "").strip()
        timestamp = str(properties.get("timestamp") or "").strip()
        icon = str(properties.get("icon") or "").strip()

        return {
            "temperature_f": temperature_f,
            "humidity_percent": None if humidity is None else round(humidity),
            "condition": condition or "Current conditions",
            "timestamp": timestamp,
            "icon": icon,
        }

    def refresh_weather_unlocked(settings):
        zip_code = settings.get("zip_code")

        if not zip_code:
            return {}

        point = zip_to_point(zip_code)
        points = fetch_json(f"https://api.weather.gov/points/{point['latitude']:.4f},{point['longitude']:.4f}")
        properties = points.get("properties") if isinstance(points, dict) else {}
        stations_url = properties.get("observationStations") if isinstance(properties, dict) else ""

        if not stations_url:
            raise RuntimeError("NOAA did not return an observation station URL")

        station_data = fetch_json(stations_url)
        features = station_data.get("features") if isinstance(station_data, dict) else []
        stations = sorted_stations(features if isinstance(features, list) else [], point)

        if not stations:
            raise RuntimeError("NOAA returned no nearby observation stations")

        observation = None
        selected_station = None
        checked_stations = []

        for station in stations[:8]:
            checked_stations.append(station)

            try:
                observation = current_observation_from_station(station)
            except Exception:
                observation = None

            if observation:
                selected_station = station
                break

        if not observation or not selected_station:
            raise RuntimeError("NOAA nearby stations did not return a usable current temperature")

        weather_cache = {
            "ok": True,
            "zip_code": zip_code,
            "source": NOAA_LABEL,
            "lookup_source": ZIP_LOOKUP_LABEL,
            "station_source": NOAA_STATION_LABEL,
            "updated_at": now_epoch(),
            "location": point,
            "station": selected_station,
            "stations_checked": checked_stations,
            "temperature_f": observation.get("temperature_f"),
            "humidity_percent": observation.get("humidity_percent"),
            "condition": observation.get("condition") or "Current conditions",
            "timestamp": observation.get("timestamp") or "",
            "icon": observation.get("icon") or "",
            "error": "",
        }

        if settings.get("air_quality_source") == AIRNOW_AQI_SOURCE:
            try:
                weather_cache["air_quality"] = airnow_air_quality_unlocked(settings, point)
            except Exception as exc:
                weather_cache["air_quality"] = {
                    "aqi": None,
                    "label": "Unavailable",
                    "parameter": "",
                    "dominant_pollutant": "",
                    "pollutants": [],
                    "reporting_area": "",
                    "source": AIRNOW_AQI_LABEL,
                    "source_id": AIRNOW_AQI_SOURCE,
                    "timestamp": "",
                    "updated_at": now_epoch(),
                    "error": str(exc),
                }
        else:
            weather_cache["air_quality"] = {}

        return weather_cache

    def safe_float(value):
        try:
            return float(value)
        except Exception:
            return None

    def average(values):
        clean = [safe_float(value) for value in values]
        clean = [value for value in clean if value is not None]
        return None if not clean else sum(clean) / len(clean)

    def temp_text(value):
        return "—" if value is None else f"{round(float(value))}°F"

    def percent_text(value):
        return "—" if value is None else f"{round(float(value))}%"

    def indoor_temp_status(value):
        if value is None:
            return "Unavailable"
        if value < 65:
            return "Cool"
        if value > 78:
            return "Warm"
        return "Comfort"

    def humidity_status(value):
        if value is None:
            return "Unavailable"
        if value < 30:
            return "Dry"
        if value > 60:
            return "Humid"
        return "Normal"

    def aqi_status(value):
        if value is None:
            return "Unavailable"
        if value <= 50:
            return "Good"
        if value <= 100:
            return "Moderate"
        if value <= 150:
            return "Unhealthy for Sensitive Groups"
        if value <= 200:
            return "Unhealthy"
        if value <= 300:
            return "Very Unhealthy"
        return "Hazardous"

    def aqi_display_label(value, label):
        if value is not None and 100 < value <= 150:
            return "Poor"
        return str(label or aqi_status(value))

    def aqi_color(value):
        if value is None:
            return ""
        if value <= 50:
            return "#00E400"
        if value <= 100:
            return "#FFFF00"
        if value <= 150:
            return "#FF7E00"
        if value <= 200:
            return "#FF0000"
        if value <= 300:
            return "#8F3F97"
        return "#7E0023"

    def airnow_pollutant_name(value):
        value = str(value or "").strip().upper()
        return {
            "OZONE": "Ozone",
            "NO2": "Nitrogen dioxide",
            "SO2": "Sulphur dioxide",
            "CO": "Carbon monoxide",
        }.get(value, value)

    def airnow_air_quality_unlocked(settings, point):
        if settings.get("air_quality_source") != AIRNOW_AQI_SOURCE:
            return {}

        reporting_areas = {}

        for line in fetch_text(AIRNOW_REPORTING_AREA_URL).splitlines():
            fields = line.split("|")

            if len(fields) < 17 or fields[5] != "O":
                continue

            area_latitude = safe_float(fields[9])
            area_longitude = safe_float(fields[10])
            aqi = safe_float(fields[12])

            if area_latitude is None or area_longitude is None or aqi is None:
                continue

            area_key = (fields[7], fields[8], area_latitude, area_longitude)
            area = reporting_areas.setdefault(area_key, {
                "name": str(fields[7] or "").strip(),
                "state": str(fields[8] or "").strip(),
                "latitude": area_latitude,
                "longitude": area_longitude,
                "pollutants": [],
            })
            area["pollutants"].append({
                "name": airnow_pollutant_name(fields[11]),
                "aqi": round(aqi),
                "label": str(fields[13] or "").strip() or aqi_status(aqi),
                "timestamp": " ".join(part for part in (fields[1], fields[2], fields[3]) if part).strip(),
            })

        if not reporting_areas:
            raise RuntimeError("AirNow did not return current AQI observations")

        selected = min(
            reporting_areas.values(),
            key=lambda area: distance_miles(
                point["latitude"],
                point["longitude"],
                area["latitude"],
                area["longitude"],
            ),
        )
        pollutants = sorted(selected["pollutants"], key=lambda item: item["aqi"], reverse=True)
        dominant = pollutants[0]
        reporting_area = ", ".join(part for part in (selected["name"], selected["state"]) if part)

        return {
            "aqi": dominant["aqi"],
            "label": dominant["label"],
            "parameter": dominant["name"],
            "dominant_pollutant": dominant["name"],
            "pollutants": pollutants,
            "reporting_area": reporting_area,
            "source": AIRNOW_AQI_LABEL,
            "source_id": AIRNOW_AQI_SOURCE,
            "timestamp": dominant["timestamp"],
            "updated_at": now_epoch(),
            "error": "",
        }

    def snapshot_clients_unlocked():
        if not isinstance(clients, dict):
            return []

        return [dict(client) for client in clients.values() if isinstance(client, dict)]

    def client_snapshot_list(client_snapshots=None):
        if isinstance(client_snapshots, list):
            return [client for client in client_snapshots if isinstance(client, dict)]

        if state_lock:
            with state_lock:
                return snapshot_clients_unlocked()

        return snapshot_clients_unlocked()

    def first_number(data, keys):
        if not isinstance(data, dict):
            return None

        for key in keys:
            number = safe_float(data.get(key))

            if number is not None:
                return number

        return None

    def client_payloads(client):
        payloads = [client]

        for key in ("environment", "telemetry", "sensor", "sensors", "readings"):
            value = client.get(key)

            if isinstance(value, dict):
                payloads.append(value)

        return payloads

    def client_number(client, keys):
        for payload in client_payloads(client):
            number = first_number(payload, keys)

            if number is not None:
                return number

        return None

    def client_temperature_f(client):
        temperature_f = client_number(client, (
            "temperature_f",
            "temperatureF",
            "temp_f",
            "tempF",
            "ambient_temperature_f",
            "ambientTemperatureF",
        ))

        if temperature_f is not None:
            return round(temperature_f, 1)

        temperature_c = client_number(client, (
            "temperature_c",
            "temperatureC",
            "temp_c",
            "tempC",
            "ambient_temperature_c",
            "ambientTemperatureC",
        ))

        return c_to_f(temperature_c)

    def client_humidity_percent(client):
        humidity = client_number(client, (
            "humidity_percent",
            "humidityPercent",
            "relative_humidity",
            "relativeHumidity",
            "humidity",
        ))

        return None if humidity is None else round(humidity, 1)

    def indoor_client_source(client):
        source = str(client.get("source") or "").strip().lower()
        device_id = str(client.get("deviceID") or "").strip().lower()

        if source == "matter" or device_id.startswith("matter:"):
            return MATTER_LABEL

        return "Local sensor"

    def indoor_source_label(devices):
        sources = []

        for device in devices:
            source = str(device.get("source") or "").strip()

            if source and source not in sources:
                sources.append(source)

        if not sources:
            return "No indoor sensor"

        return " + ".join(sources)

    def indoor_environment_devices(client_snapshots=None):
        devices = []

        for client in client_snapshot_list(client_snapshots):
            temperature_f = client_temperature_f(client)
            humidity = client_humidity_percent(client)

            if temperature_f is None and humidity is None:
                continue

            devices.append({
                "deviceID": client.get("deviceID", ""),
                "name": client.get("clientName") or client.get("matter_node_label") or client.get("model") or "Environment sensor",
                "zone_name": client.get("zone_name") or client.get("zoneName") or "",
                "temperature_f": temperature_f,
                "humidity_percent": humidity,
                "source": indoor_client_source(client),
                "updated_at": client.get("matter_last_sync_at") or client.get("last_seen") or 0,
            })

        return devices

    def configured_aqi(settings, cache, client_snapshots=None):
        source = str(settings.get("air_quality_source") or "none").strip().lower()

        if source != AIRNOW_AQI_SOURCE:
            return {
                "aqi": None,
                "label": "Unavailable",
                "parameter": "",
                "dominant_pollutant": "",
                "pollutants": [],
                "reporting_area": "",
                "source": "Not configured",
                "source_id": "none",
                "timestamp": "",
                "updated_at": 0,
                "error": "",
            }

        air_quality = cache.get("air_quality") if isinstance(cache, dict) else {}

        if isinstance(air_quality, dict) and air_quality.get("source_id") == AIRNOW_AQI_SOURCE:
            aqi = safe_float(air_quality.get("aqi"))
            return {
                "aqi": None if aqi is None else round(aqi),
                "label": str(air_quality.get("label") or aqi_status(aqi)),
                "parameter": str(air_quality.get("parameter") or air_quality.get("dominant_pollutant") or ""),
                "dominant_pollutant": str(air_quality.get("dominant_pollutant") or air_quality.get("parameter") or ""),
                "pollutants": air_quality.get("pollutants") if isinstance(air_quality.get("pollutants"), list) else [],
                "reporting_area": str(air_quality.get("reporting_area") or ""),
                "source": str(air_quality.get("source") or AIRNOW_AQI_LABEL),
                "source_id": str(air_quality.get("source_id") or AIRNOW_AQI_SOURCE),
                "timestamp": str(air_quality.get("timestamp") or ""),
                "updated_at": air_quality.get("updated_at", 0),
                "error": str(air_quality.get("error") or ""),
            }

        return {
            "aqi": None,
            "label": "Unavailable",
            "parameter": "",
            "dominant_pollutant": "",
            "pollutants": [],
            "reporting_area": "",
            "source": AIRNOW_AQI_LABEL,
            "source_id": AIRNOW_AQI_SOURCE,
            "timestamp": "",
            "updated_at": 0,
            "error": "Refresh needed",
        }

    def environment_snapshot(client_snapshots=None):
        with lock:
            state = read_state_unlocked()

        settings = state.get("settings")
        cache = state.get("weather_cache") if isinstance(state.get("weather_cache"), dict) else {}
        client_snapshots = client_snapshot_list(client_snapshots)
        devices = indoor_environment_devices(client_snapshots)
        indoor_f = average(device.get("temperature_f") for device in devices)
        indoor_humidity = average(device.get("humidity_percent") for device in devices)
        indoor_f = None if indoor_f is None else round(indoor_f, 1)
        indoor_humidity = None if indoor_humidity is None else round(indoor_humidity)
        air_quality = configured_aqi(settings, cache, client_snapshots)
        aqi = safe_float(air_quality.get("aqi"))
        outdoor_f = safe_float(cache.get("temperature_f"))
        outdoor_humidity = safe_float(cache.get("humidity_percent"))
        outdoor_condition = str(cache.get("condition") or cache.get("error") or ("Set ZIP code" if not settings.get("zip_code") else "Unavailable"))

        snapshot = {
            "ok": True,
            "settings": settings,
            "sources": [
                {"id": "matter", "label": MATTER_LABEL, "kind": "indoor"},
                {"id": NOAA_SOURCE, "label": NOAA_LABEL, "kind": "weather"},
                {"id": "zip", "label": ZIP_LOOKUP_LABEL, "kind": "location"},
                {"id": "noaa_station", "label": NOAA_STATION_LABEL, "kind": "station"},
                {"id": "none", "label": "Not configured", "kind": "air_quality"},
                {"id": AIRNOW_AQI_SOURCE, "label": AIRNOW_AQI_LABEL, "kind": "air_quality"},
            ],
            "indoor": {
                "temperature_f": indoor_f,
                "temperature_text": temp_text(indoor_f),
                "temperature_status": indoor_temp_status(indoor_f),
                "humidity_percent": indoor_humidity,
                "humidity_text": percent_text(indoor_humidity),
                "humidity_status": humidity_status(indoor_humidity),
                "source": indoor_source_label(devices),
                "devices": devices,
            },
            "air_quality": {
                "aqi": None if aqi is None else round(aqi),
                "aqi_text": "—" if aqi is None else str(round(aqi)),
                "label": aqi_display_label(aqi, air_quality.get("label")),
                "official_label": str(air_quality.get("label") or aqi_status(aqi)),
                "color": aqi_color(aqi),
                "parameter": str(air_quality.get("parameter") or ""),
                "dominant_pollutant": str(air_quality.get("dominant_pollutant") or air_quality.get("parameter") or ""),
                "pollutants": air_quality.get("pollutants") if isinstance(air_quality.get("pollutants"), list) else [],
                "reporting_area": str(air_quality.get("reporting_area") or ""),
                "source": str(air_quality.get("source") or "Not configured"),
                "source_id": str(air_quality.get("source_id") or "none"),
                "updated_at": air_quality.get("updated_at", 0),
                "timestamp": str(air_quality.get("timestamp") or ""),
                "error": str(air_quality.get("error") or ""),
            },
            "outdoor": {
                "temperature_f": None if outdoor_f is None else round(outdoor_f, 1),
                "temperature_text": temp_text(outdoor_f),
                "humidity_percent": None if outdoor_humidity is None else round(outdoor_humidity),
                "humidity_text": percent_text(outdoor_humidity),
                "condition": outdoor_condition,
                "source": str(cache.get("source") or NOAA_LABEL),
                "lookup_source": str(cache.get("lookup_source") or ZIP_LOOKUP_LABEL),
                "station_source": str(cache.get("station_source") or NOAA_STATION_LABEL),
                "updated_at": cache.get("updated_at", 0),
                "timestamp": str(cache.get("timestamp") or ""),
                "location": cache.get("location") if isinstance(cache.get("location"), dict) else {},
                "station": cache.get("station") if isinstance(cache.get("station"), dict) else {},
                "stations_checked": cache.get("stations_checked") if isinstance(cache.get("stations_checked"), list) else [],
                "icon": str(cache.get("icon") or ""),
                "error": str(cache.get("error") or ""),
            },
        }

        snapshot["cards"] = [
            {"id": "indoor_temp", "label": "Indoor", "value": snapshot["indoor"]["temperature_text"], "status": snapshot["indoor"]["temperature_status"], "icon": "thermometer", "source": snapshot["indoor"]["source"]},
            {"id": "humidity", "label": "Humidity", "value": snapshot["indoor"]["humidity_text"], "status": snapshot["indoor"]["humidity_status"], "icon": "droplet", "source": snapshot["indoor"]["source"]},
            {"id": "air_quality", "label": "Air Quality", "value": snapshot["air_quality"]["label"], "status": "AQI " + str(aqi) if aqi is not None else snapshot["air_quality"]["source"], "icon": "leaf", "source": snapshot["air_quality"]["source"]},
            {"id": "outdoor", "label": "Outdoor", "value": snapshot["outdoor"]["temperature_text"], "status": snapshot["outdoor"]["condition"], "icon": "sun", "source": snapshot["outdoor"]["source"]},
        ]
        return snapshot

    def refresh_weather():
        with lock:
            state = read_state_unlocked()
            settings = dict(state["settings"])

        try:
            weather_cache = refresh_weather_unlocked(settings)

        except Exception as exc:
            weather_cache = {
                "ok": False,
                "zip_code": settings.get("zip_code", ""),
                "source": NOAA_LABEL,
                "lookup_source": ZIP_LOOKUP_LABEL,
                "station_source": NOAA_STATION_LABEL,
                "updated_at": now_epoch(),
                "error": str(exc),
            }
            app.logger.exception("Environment weather refresh failed")

        with lock:
            state = read_state_unlocked()
            current_settings = state["settings"]

            if (
                current_settings.get("zip_code") == settings.get("zip_code")
                and current_settings.get("weather_source") == settings.get("weather_source")
                and current_settings.get("air_quality_source") == settings.get("air_quality_source")
            ):
                state["weather_cache"] = weather_cache
                write_state_unlocked(state)

        if callable(broadcast_state):
            broadcast_state()

        return environment_snapshot()

    def environment_loop():
        initial_delay = 5.0
        check_interval = 60.0

        if stop_event.wait(initial_delay):
            return

        while not stop_event.is_set():
            try:
                with lock:
                    state = read_state_unlocked()
                    settings = state["settings"]
                    cache = state.get("weather_cache") if isinstance(state.get("weather_cache"), dict) else {}
                    air_quality_cache = cache.get("air_quality") if isinstance(cache.get("air_quality"), dict) else {}
                    air_quality_missing = (
                        settings.get("air_quality_source") == AIRNOW_AQI_SOURCE
                        and (
                            not air_quality_cache.get("updated_at")
                            or air_quality_cache.get("source_id") != AIRNOW_AQI_SOURCE
                        )
                    )
                    should_refresh = bool(
                        settings.get("zip_code")
                        and (
                            air_quality_missing
                            or now_epoch() - float(cache.get("updated_at") or 0) >= settings.get("refresh_seconds", DEFAULT_REFRESH_SECONDS)
                        )
                    )

                if should_refresh:
                    refresh_weather()
            except Exception:
                app.logger.exception("Environment weather loop failed")

            if stop_event.wait(check_interval):
                return

    def matter_state_debug():
        exists = json_exists(matter_state_file)
        summary = {
            "path": str(matter_state_file),
            "exists": exists,
        }

        if not exists:
            return summary

        try:
            data = read_json(matter_state_file)
        except Exception as exc:
            summary["error"] = str(exc)
            return summary

        last_command = data.get("last_command") if isinstance(data, dict) else {}
        nodes = data.get("nodes") if isinstance(data, dict) else {}
        children = []

        if isinstance(nodes, dict):
            for node_id, node in nodes.items():
                if not isinstance(node, dict):
                    continue

                for child in node.get("matter_children") or []:
                    if not isinstance(child, dict):
                        continue

                    children.append({
                        "node_id": node_id,
                        "endpoint": child.get("endpoint"),
                        "kinds": child.get("kinds"),
                        "temperature_raw": child.get("temperature_raw"),
                        "temperature_c": child.get("temperature_c"),
                        "humidity_raw": child.get("humidity_raw"),
                        "humidity_percent": child.get("humidity_percent"),
                    })

        summary.update({
            "enabled": data.get("enabled") if isinstance(data, dict) else None,
            "last_command": {
                "command": last_command.get("command") if isinstance(last_command, dict) else None,
                "ok": last_command.get("ok") if isinstance(last_command, dict) else None,
                "returncode": last_command.get("returncode") if isinstance(last_command, dict) else None,
                "stdout_tail": str(last_command.get("stdout") or "")[-1200:] if isinstance(last_command, dict) else "",
                "stderr_tail": str(last_command.get("stderr") or "")[-1200:] if isinstance(last_command, dict) else "",
            },
            "children": children,
        })
        return summary

    def environment_debug_payload():
        with lock:
            state = read_state_unlocked()

        client_snapshots = client_snapshot_list()
        candidates = []

        for client in client_snapshots:
            source = str(client.get("source") or "").strip().lower()
            device_id = str(client.get("deviceID") or "").strip()
            temperature_f = client_temperature_f(client)
            humidity = client_humidity_percent(client)

            if source != "matter" and temperature_f is None and humidity is None:
                continue

            candidates.append({
                "deviceID": device_id,
                "name": client.get("clientName") or client.get("matter_node_label") or client.get("model") or "",
                "source": client.get("source"),
                "role": client.get("clientRole"),
                "zone_name": client.get("zone_name") or client.get("zoneName") or "",
                "matter_kind": client.get("matter_kind"),
                "matter_kinds": client.get("matter_kinds"),
                "temperature_c": client.get("temperature_c"),
                "temperature_f": temperature_f,
                "humidity_percent": humidity,
                "last_seen": client.get("last_seen"),
                "matter_last_sync_at": client.get("matter_last_sync_at"),
            })

        return {
            "ok": True,
            "state_file": str(state_file),
            "state_file_exists": json_exists(state_file),
            "settings": state.get("settings"),
            "weather_cache_keys": sorted((state.get("weather_cache") or {}).keys()),
            "weather_cache": state.get("weather_cache") if isinstance(state.get("weather_cache"), dict) else {},
            "client_count": len(client_snapshots),
            "indoor_devices": indoor_environment_devices(client_snapshots),
            "candidates": candidates,
            "matter_state": matter_state_debug(),
        }

    @app.get("/api/environment/debug")
    def api_environment_debug():
        return jsonify(environment_debug_payload())

    @app.get("/api/environment/status")
    def api_environment_status():
        if str(request.args.get("refresh") or "").strip().lower() in ("1", "true", "yes", "on"):
            return jsonify(refresh_weather())
        return jsonify(environment_snapshot())

    @app.get("/api/environment/settings")
    def api_environment_settings_get():
        snapshot = environment_snapshot()
        return jsonify({"ok": True, "settings": snapshot["settings"], "sources": snapshot["sources"]})

    @app.post("/api/environment/settings")
    def api_environment_settings_post():
        payload = request.get_json(silent=True) or {}
        settings = clean_settings(payload)

        with lock:
            state = read_state_unlocked()
            old = state["settings"]
            state["settings"] = settings

            if (
                old.get("zip_code") != settings.get("zip_code")
                or old.get("weather_source") != settings.get("weather_source")
                or old.get("air_quality_source") != settings.get("air_quality_source")
            ):
                state["weather_cache"] = {}

            write_state_unlocked(state)

        snapshot = environment_snapshot()

        if callable(broadcast_state):
            broadcast_state()

        return jsonify(snapshot)

    @app.post("/api/environment/refresh")
    def api_environment_refresh():
        return jsonify(refresh_weather())

    return {
        "snapshot": environment_snapshot,
        "loop": environment_loop,
        "refresh_weather": refresh_weather,
    }