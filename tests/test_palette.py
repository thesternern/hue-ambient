import pytest
from datetime import datetime, timezone
from src.palette import (
    blend_hue_descending,
    ANCHOR_POINTS,
    apply_brightness_floor,
    apply_weather_modifiers,
    blend_hue,
    compute_hsb,
    cosine_interpolate,
    get_base_hsb,
)
from src.environment import EnvironmentState

CONFIG = {
    "cloud_desaturation_strength": 0.25,
    "rain_hue_target": 215,
    "temperature_influence": 0.1,
    "clear_sky_saturation_boost": 20,
    "thunderstorm_hue_target": 265,
    "azimuth_warmth": 0.10,
    "wind_influence": 0.15,
}

# Hues in this band read as green, which looks wrong on an indoor light.
GREEN_BAND = (70, 160)
# Below this saturation any hue reads as white, so the band is safe to cross.
GREEN_SAFE_SAT = 18


def make_state(elev, clouds=0, condition="Clear", cid=800, temp=15.0,
               is_rain=False, is_snow=False, is_fog=False, azimuth=180,
               wind=2.0, visibility=10000):
    return EnvironmentState(
        sun_elevation=elev, sun_azimuth=azimuth,
        condition=condition, condition_id=cid,
        cloud_cover=clouds, temperature_c=temp,
        humidity=60, visibility_m=visibility, wind_speed_ms=wind,
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


class TestBlendHue:
    def test_zero_amount_is_identity(self):
        assert blend_hue(35, 265, 0.0) == pytest.approx(35)

    def test_full_amount_reaches_target(self):
        assert blend_hue(35, 265, 1.0) == pytest.approx(265, abs=0.01)

    def test_takes_short_path_across_zero(self):
        # 350 -> 10 should pass through 0, not walk backwards through 180.
        assert blend_hue(350, 10, 0.5) == pytest.approx(0.0, abs=0.01)

    def test_never_transits_through_cyan_amber_to_violet(self):
        # The old linear blend put amber->violet through ~190 (teal).
        for amount in [i / 20 for i in range(21)]:
            h = blend_hue(35, 265, amount)
            assert not (GREEN_BAND[0] <= h <= GREEN_BAND[1]), f"teal transit at {amount}"


class TestBlendHueDescending:
    def test_full_amount_reaches_target(self):
        assert blend_hue_descending(35, 215, 1.0) == pytest.approx(215, abs=0.01)

    def test_walks_down_through_magenta_not_green(self):
        # 35 -> 215 is almost exactly antipodal, so the "short" path is a coin
        # flip that half the time lands in green. This must never happen.
        for amount in [i / 40 for i in range(41)]:
            h = blend_hue_descending(35, 215, amount)
            assert not (GREEN_BAND[0] <= h <= GREEN_BAND[1]), f"green transit at {amount}"

    def test_direct_when_already_below_target(self):
        # Violet night base -> blue-grey rain should just slide down.
        assert blend_hue_descending(260, 215, 0.5) == pytest.approx(237.5, abs=0.01)


class TestBaseHsb:
    def test_deep_night(self):
        h, s, b = get_base_hsb(-25)
        assert 240 <= h <= 260
        assert 60 <= s <= 75
        assert 5 <= b <= 15

    def test_high_summer_sun_is_cool(self):
        h, _, b = get_base_hsb(64)
        assert 180 <= h <= 210, "peak summer sun should reach cool cyan-white"
        assert b >= 95

    def test_golden_hour_is_warm(self):
        h, s, b = get_base_hsb(8)
        assert 15 <= h <= 30
        assert b > 50

    def test_brightness_increases_with_elevation(self):
        _, _, b_night = get_base_hsb(-20)
        _, _, b_dawn = get_base_hsb(-3)
        _, _, b_noon = get_base_hsb(45)
        assert b_night < b_dawn < b_noon

    def test_winter_never_reaches_the_cool_end(self):
        # Max elevation at 49.32N in December is ~17 degrees.
        h, _, _ = get_base_hsb(17)
        assert h < 50, "winter midday should stay warm"

    def test_midday_is_not_frozen(self):
        # The old top anchor sat at 45deg, so ~6 hours a day produced an
        # identical colour. The curve must keep moving to real summer maximum.
        a = get_base_hsb(46)
        b = get_base_hsb(55)
        c = get_base_hsb(60)
        assert a != b != c
        assert abs(b[0] - a[0]) > 5

    def test_anchors_sorted_ascending(self):
        elevs = [a[0] for a in ANCHOR_POINTS]
        assert elevs == sorted(elevs)


class TestNoGreenLight:
    """The gold->cyan sweep crosses green; it must stay near-white while it does."""

    def _assert_safe(self, h, s, label):
        if GREEN_BAND[0] <= h <= GREEN_BAND[1]:
            assert s <= GREEN_SAFE_SAT, f"{label}: visible green H={h:.1f} S={s:.1f}"

    def test_base_curve_never_visibly_green(self):
        for i in range(-300, 700):
            elev = i / 10.0
            h, s, _ = get_base_hsb(elev)
            self._assert_safe(h, s, f"elev={elev}")

    def test_full_pipeline_never_visibly_green(self):
        conditions = [
            ("clear", dict(cid=800, clouds=0)),
            ("partly", dict(cid=802, clouds=50)),
            ("overcast", dict(cid=804, clouds=100)),
            ("rain", dict(cid=501, clouds=90, is_rain=True)),
            ("storm", dict(cid=200, clouds=95, is_rain=True)),
            ("snow", dict(cid=601, clouds=90, is_rain=True, is_snow=True)),
            ("fog", dict(cid=741, clouds=90, is_fog=True, visibility=400)),
        ]
        for label, kw in conditions:
            for i in range(-30, 66):
                for az in (90, 180, 270):
                    for temp in (-5.0, 15.0, 30.0):
                        st = make_state(float(i), azimuth=az, temp=temp, wind=12.0, **kw)
                        h, s, _ = compute_hsb(st, CONFIG, 1.0, 1.0, 60.0)
                        self._assert_safe(h, s, f"{label} elev={i} az={az} t={temp}")


class TestWeatherModifiers:
    def test_heavy_clouds_desaturate(self):
        base = get_base_hsb(30)
        _, s_base, _ = base
        _, s_cloudy, _ = apply_weather_modifiers(base, make_state(30, clouds=100), CONFIG)
        assert s_cloudy < s_base

    def test_rain_moves_toward_blue_grey_not_yellow(self):
        # The old code did `h += 15` on an amber base, landing at ~52 (yellow-green).
        base = get_base_hsb(18)
        h_base = base[0]
        rain = make_state(18, clouds=100, condition="Rain", cid=501, is_rain=True)
        h_rain, s_rain, _ = apply_weather_modifiers(base, rain, CONFIG)
        assert h_rain != h_base
        assert not (40 <= h_rain <= 160), f"rain drifted to yellow/green: {h_rain:.1f}"
        assert s_rain < base[1], "rain should mute the colour"

    def test_thunderstorm_does_not_go_cyan(self):
        # The old linear blend produced H~189 (teal) from an amber base.
        base = get_base_hsb(18)
        storm = make_state(18, clouds=95, condition="Thunderstorm", cid=200, is_rain=True)
        h_storm, _, b_storm = apply_weather_modifiers(base, storm, CONFIG)
        assert not (GREEN_BAND[0] <= h_storm <= GREEN_BAND[1]), f"teal storm: {h_storm:.1f}"
        assert 260 <= h_storm <= 345, f"storm should be magenta/violet, got {h_storm:.1f}"
        assert b_storm < base[2]

    def test_clouds_do_not_push_hue_to_yellow(self):
        base = get_base_hsb(18)
        h_base = base[0]
        h_cloudy, _, _ = apply_weather_modifiers(base, make_state(18, clouds=100), CONFIG)
        # Only the tiny temperature nudge may move it; no deliberate hue push.
        assert abs(h_cloudy - h_base) < 3

    def test_snow_tints_lavender(self):
        base = get_base_hsb(10)
        snow = make_state(10, clouds=90, condition="Snow", cid=601,
                          is_rain=True, is_snow=True, temp=-2.0)
        h_snow, s_snow, _ = apply_weather_modifiers(base, snow, CONFIG)
        assert s_snow < base[1]
        assert not (GREEN_BAND[0] <= h_snow <= GREEN_BAND[1])


class TestSolarAsymmetry:
    def test_morning_and_afternoon_differ(self):
        # Same sun height either side of noon used to give an identical colour.
        morning = compute_hsb(make_state(30, azimuth=120), CONFIG, 1.0, 1.0, 60.0)
        afternoon = compute_hsb(make_state(30, azimuth=240), CONFIG, 1.0, 1.0, 60.0)
        assert morning != afternoon

    def test_afternoon_is_warmer_than_morning(self):
        h_morning, _, _ = compute_hsb(make_state(30, azimuth=120), CONFIG, 1.0, 1.0, 60.0)
        h_afternoon, _, _ = compute_hsb(make_state(30, azimuth=240), CONFIG, 1.0, 1.0, 60.0)
        assert h_afternoon < h_morning, "afternoon should sit closer to amber"

    def test_disabled_when_strength_zero(self):
        cfg = dict(CONFIG, azimuth_warmth=0.0)
        morning = compute_hsb(make_state(30, azimuth=120), cfg, 1.0, 1.0, 60.0)
        afternoon = compute_hsb(make_state(30, azimuth=240), cfg, 1.0, 1.0, 60.0)
        assert morning == afternoon

    def test_no_effect_at_night(self):
        a = compute_hsb(make_state(-15, azimuth=20), CONFIG, 1.0, 1.0, 60.0)
        b = compute_hsb(make_state(-15, azimuth=340), CONFIG, 1.0, 1.0, 60.0)
        assert a == b


class TestBrightnessFloor:
    def test_zero_floor_is_identity(self):
        assert apply_brightness_floor(42.0, 0.0) == 42.0

    def test_compresses_into_range(self):
        assert apply_brightness_floor(0.0, 60.0) == pytest.approx(60.0)
        assert apply_brightness_floor(100.0, 60.0) == pytest.approx(100.0)
        assert apply_brightness_floor(50.0, 60.0) == pytest.approx(80.0)

    def test_night_arc_survives_the_floor(self):
        # A hard clamp flattened deep night, twilight and dawn to the same value.
        deep = compute_hsb(make_state(-20), CONFIG, 1.0, 1.0, 60.0)[2]
        twilight = compute_hsb(make_state(-12), CONFIG, 1.0, 1.0, 60.0)[2]
        dawn = compute_hsb(make_state(-3), CONFIG, 1.0, 1.0, 60.0)[2]
        assert deep < twilight < dawn
        assert deep >= 60.0, "should still be usably bright"

    def test_never_below_floor(self):
        for elev in range(-30, 66):
            b = compute_hsb(make_state(float(elev), clouds=100, cid=200, is_rain=True),
                            CONFIG, 1.0, 1.0, 60.0)[2]
            assert b >= 60.0


class TestComputeHsb:
    def test_returns_valid_ranges(self):
        for elev in range(-30, 66, 3):
            for clouds in (0, 50, 100):
                h, s, b = compute_hsb(make_state(float(elev), clouds=clouds), CONFIG)
                assert 0 <= h <= 360
                assert 0 <= s <= 100
                assert 1 <= b <= 100

    def test_multipliers_applied(self):
        state = make_state(30)
        h1, s1, b1 = compute_hsb(state, CONFIG, brightness_multiplier=1.0, saturation_multiplier=1.0)
        h2, s2, b2 = compute_hsb(state, CONFIG, brightness_multiplier=0.5, saturation_multiplier=0.5)
        assert b2 < b1
        assert s2 < s1

    def test_idempotent(self):
        state = make_state(22, clouds=40, azimuth=200, wind=6.0)
        first = compute_hsb(state, CONFIG, 1.0, 1.0, 60.0)
        for _ in range(5):
            assert compute_hsb(state, CONFIG, 1.0, 1.0, 60.0) == first

    def test_defaults_when_no_config(self):
        h, s, b = compute_hsb(make_state(30))
        assert 0 <= h <= 360 and 0 <= s <= 100 and 1 <= b <= 100
