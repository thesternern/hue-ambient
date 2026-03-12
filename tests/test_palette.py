import pytest
from datetime import datetime, timezone
from src.palette import cosine_interpolate, get_base_hsb, apply_weather_modifiers, compute_hsb
from src.environment import EnvironmentState


def make_state(elev, clouds=0, condition="Clear", cid=800, temp=15.0,
               is_rain=False, is_snow=False, is_fog=False):
    return EnvironmentState(
        sun_elevation=elev, sun_azimuth=180,
        condition=condition, condition_id=cid,
        cloud_cover=clouds, temperature_c=temp,
        humidity=60, visibility_m=10000, wind_speed_ms=2.0,
        is_rain=is_rain, is_snow=is_snow, is_fog=is_fog,
        timestamp=datetime.now(timezone.utc),
    )


class TestCosineInterpolate:
    def test_at_start(self):
        assert cosine_interpolate(0.0, 10.0, 0.0) == 0.0

    def test_at_end(self):
        assert cosine_interpolate(0.0, 10.0, 1.0) == 10.0

    def test_at_midpoint_symmetric(self):
        result = cosine_interpolate(0.0, 10.0, 0.5)
        assert abs(result - 5.0) < 0.01


class TestBaseHsb:
    def test_deep_night(self):
        h, s, b = get_base_hsb(-25)
        assert 240 <= h <= 260
        assert 60 <= s <= 70
        assert 8 <= b <= 15

    def test_midday(self):
        h, s, b = get_base_hsb(45)
        assert 45 <= h <= 55
        assert 40 <= s <= 50
        assert 85 <= b <= 100

    def test_golden_hour(self):
        h, s, b = get_base_hsb(5)
        assert 25 <= h <= 45  # warm amber/peach
        assert b > 50

    def test_brightness_increases_with_elevation(self):
        _, _, b_night = get_base_hsb(-20)
        _, _, b_dawn = get_base_hsb(-3)
        _, _, b_noon = get_base_hsb(45)
        assert b_night < b_dawn < b_noon


class TestWeatherModifiers:
    def test_heavy_clouds_desaturate(self):
        base = get_base_hsb(30)
        _, s_base, _ = base
        config = {
            "cloud_desaturation_strength": 0.25,
            "rain_hue_shift": 15,
            "temperature_influence": 0.1,
        }
        _, s_cloudy, _ = apply_weather_modifiers(base, make_state(30, clouds=100), config)
        assert s_cloudy < s_base

    def test_rain_shifts_hue(self):
        base = get_base_hsb(30)
        h_base, _, _ = base
        config = {
            "cloud_desaturation_strength": 0.25,
            "rain_hue_shift": 15,
            "temperature_influence": 0.1,
        }
        rain_state = make_state(30, clouds=80, condition="Rain", cid=501, is_rain=True)
        h_rain, _, _ = apply_weather_modifiers(base, rain_state, config)
        assert h_rain != h_base


class TestComputeHsb:
    def test_returns_valid_ranges(self):
        state = make_state(30)
        h, s, b = compute_hsb(state)
        assert 0 <= h <= 360
        assert 0 <= s <= 100
        assert 0 <= b <= 100

    def test_multipliers_applied(self):
        state = make_state(30)
        h1, s1, b1 = compute_hsb(state, brightness_multiplier=1.0, saturation_multiplier=1.0)
        h2, s2, b2 = compute_hsb(state, brightness_multiplier=0.5, saturation_multiplier=0.5)
        assert b2 < b1
        assert s2 < s1
