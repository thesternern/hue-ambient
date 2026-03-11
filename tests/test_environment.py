import pytest
from datetime import datetime
import zoneinfo
from src.environment import get_sun_position, EnvironmentState, parse_weather

VANCOUVER_TZ = zoneinfo.ZoneInfo("America/Vancouver")


class TestSunPosition:
    def test_summer_noon_elevation_positive(self):
        # Summer solstice noon in Vancouver — sun should be high
        dt = datetime(2025, 6, 21, 12, 0, tzinfo=VANCOUVER_TZ)
        elev, azimuth = get_sun_position(dt, lat=49.32, lon=-123.0724)
        assert elev > 50  # summer max ~64°

    def test_winter_noon_elevation_low(self):
        # Winter solstice noon — sun should be low
        dt = datetime(2025, 12, 21, 12, 0, tzinfo=VANCOUVER_TZ)
        elev, azimuth = get_sun_position(dt, lat=49.32, lon=-123.0724)
        assert 10 < elev < 25  # winter max ~17°

    def test_midnight_elevation_negative(self):
        dt = datetime(2025, 6, 21, 0, 0, tzinfo=VANCOUVER_TZ)
        elev, azimuth = get_sun_position(dt, lat=49.32, lon=-123.0724)
        assert elev < 0

    def test_azimuth_range(self):
        dt = datetime(2025, 6, 21, 12, 0, tzinfo=VANCOUVER_TZ)
        elev, azimuth = get_sun_position(dt, lat=49.32, lon=-123.0724)
        assert 0 <= azimuth <= 360


class TestParseWeather:
    def _owm_response(self, condition="Clear", cid=800, clouds=0, temp=15.0):
        return {
            "weather": [{"main": condition, "id": cid, "description": ""}],
            "clouds": {"all": clouds},
            "main": {"temp": temp, "humidity": 60},
            "visibility": 10000,
            "wind": {"speed": 3.0},
        }

    def test_clear_day(self):
        w = parse_weather(self._owm_response())
        assert w["condition"] == "Clear"
        assert w["is_rain"] is False
        assert w["is_snow"] is False

    def test_rain_detected(self):
        w = parse_weather(self._owm_response("Rain", cid=501, clouds=80))
        assert w["is_rain"] is True
        assert w["cloud_cover"] == 80.0

    def test_snow_detected(self):
        w = parse_weather(self._owm_response("Snow", cid=601, clouds=90))
        assert w["is_snow"] is True
        assert w["is_rain"] is True  # snow range is subset of rain range

    def test_fog_detected(self):
        w = parse_weather(self._owm_response("Mist", cid=701))
        assert w["is_fog"] is True
