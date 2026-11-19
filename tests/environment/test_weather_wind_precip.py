"""Wind and chance-of-rain fields on the outdoor weather snapshot.

Synthetic NOAA responses only; nothing contacts the network.
"""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from server_core.io import flush_json_writes

from subsystems.environment import environment_routes as er


class FakeResponse(io.BytesIO):
    def __init__(self, url, payload):
        super().__init__(json.dumps(payload).encode())
        self._url = url

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def routes(responses):
    def opener(req, timeout=8):
        url = req.full_url
        if url not in responses:
            raise OSError("unexpected url " + url)
        value = responses[url]
        if isinstance(value, Exception):
            raise value
        return FakeResponse(url, value)

    return opener


STATION = "https://api.weather.gov/stations/KTST"
HOURLY = "https://api.weather.gov/gridpoints/TST/1,1/forecast/hourly"


def base_responses(wind, hourly):
    return {
        "https://api.zippopotam.us/us/12345": {"places": [{"latitude": "40.0", "longitude": "-75.0", "place name": "T", "state abbreviation": "PA"}]},
        "https://api.weather.gov/points/40.0000,-75.0000": {"properties": {
            "observationStations": "https://api.weather.gov/points/stations", "forecastHourly": HOURLY}},
        "https://api.weather.gov/points/stations": {"features": [{
            "id": STATION, "properties": {"stationIdentifier": "KTST", "name": "Test"},
            "geometry": {"coordinates": [-75.0, 40.0]}}]},
        STATION + "/observations/latest": {"properties": {
            "temperature": {"value": 10}, "relativeHumidity": {"value": 63.4},
            "textDescription": "Light Rain", "timestamp": "t", "icon": "",
            **wind}},
        HOURLY: hourly,
    }


class WindPrecipTests(unittest.TestCase):
    def snapshot(self, responses):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        # Runs before the directory is removed: no queued write may outlive it.
        self.addCleanup(flush_json_writes)
        root = Path(tmp.name)
        handlers = er.register_environment_routes(Flask(__name__), {
            "state_file": root / "env.json", "matter_state_file": root / "matter.json",
            "now_epoch": lambda: 1})
        with patch.object(er.REMOTE_OPENER, "open", routes(responses)):
            er.write_json_atomic(root / "env.json", {"settings": {
                "zip_code": "12345", "weather_source": "noaa",
                "air_quality_source": "none", "refresh_seconds": 900}, "weather_cache": {}})
            handlers["refresh_weather"]()
        return handlers["snapshot"]()["outdoor"]

    def test_wind_kmh_is_converted_to_mph_with_compass_point(self):
        out = self.snapshot(base_responses(
            {"windSpeed": {"unitCode": "wmoUnit:km_h-1", "value": 32.2},
             "windDirection": {"value": 315}},
            {"properties": {"periods": [{"probabilityOfPrecipitation": {"value": 80}}]}}))
        self.assertEqual(out["wind_mph"], 20)
        self.assertEqual(out["wind_direction"], "NW")
        self.assertEqual(out["precip_chance_percent"], 80)

    def test_wind_in_metres_per_second_is_converted(self):
        out = self.snapshot(base_responses(
            {"windSpeed": {"unitCode": "wmoUnit:m_s-1", "value": 5}, "windDirection": {"value": 0}},
            {"properties": {"periods": [{"probabilityOfPrecipitation": {"value": 0}}]}}))
        self.assertEqual(out["wind_mph"], 11)
        self.assertEqual(out["wind_direction"], "N")
        self.assertEqual(out["precip_chance_percent"], 0)

    def test_missing_wind_and_failed_forecast_leave_none_not_error(self):
        out = self.snapshot(base_responses({}, OSError("down")))
        self.assertIsNone(out["wind_mph"])
        self.assertEqual(out["wind_direction"], "")
        self.assertIsNone(out["precip_chance_percent"])
        self.assertEqual(out["temperature_f"], 50.0)
        self.assertEqual(out["error"], "")

    def test_null_precip_value_is_none(self):
        out = self.snapshot(base_responses({}, {"properties": {"periods": [{"probabilityOfPrecipitation": {"value": None}}]}}))
        self.assertIsNone(out["precip_chance_percent"])


if __name__ == "__main__":
    unittest.main()
