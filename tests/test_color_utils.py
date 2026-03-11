import pytest
from src.color_utils import hsb_to_rgb, rgb_to_xy, hsb_to_hue_api


class TestHsbToRgb:
    def test_red(self):
        r, g, b = hsb_to_rgb(0, 100, 100)
        assert r == 255 and g == 0 and b == 0

    def test_white(self):
        r, g, b = hsb_to_rgb(0, 0, 100)
        assert r == 255 and g == 255 and b == 255

    def test_black(self):
        r, g, b = hsb_to_rgb(0, 0, 0)
        assert r == 0 and g == 0 and b == 0

    def test_warm_amber(self):
        r, g, b = hsb_to_rgb(35, 70, 80)
        assert r > g > b  # amber has more red than green than blue


class TestRgbToXy:
    def test_output_range(self):
        x, y = rgb_to_xy(255, 0, 0)
        assert 0.0 <= x <= 1.0
        assert 0.0 <= y <= 1.0

    def test_white_xy(self):
        x, y = rgb_to_xy(255, 255, 255)
        # D65 white point approximately (0.313, 0.329)
        assert 0.28 < x < 0.35
        assert 0.29 < y < 0.37


class TestHsbToHueApi:
    def test_output_ranges(self):
        hue_val, sat_val, bri_val = hsb_to_hue_api(180, 50, 75)
        assert 0 <= hue_val <= 65535
        assert 0 <= sat_val <= 254
        assert 1 <= bri_val <= 254

    def test_full_saturation(self):
        _, sat_val, _ = hsb_to_hue_api(0, 100, 100)
        assert sat_val == 254

    def test_full_brightness(self):
        _, _, bri_val = hsb_to_hue_api(0, 0, 100)
        assert bri_val == 254
