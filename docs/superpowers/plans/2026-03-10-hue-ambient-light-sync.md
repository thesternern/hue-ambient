# Hue Ambient Light Sync — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python service that fetches weather/sun data and drives Philips Hue lights to artistically reflect outdoor conditions every 15 minutes.

**Architecture:** A pipeline — `environment.py` gathers sun position + weather data into an `EnvironmentState`; `palette.py` maps that state to HSB values via a sun-elevation curve with weather modifiers; `hue_api.py` converts and pushes those values to the Hue Remote API. `main.py` wires the pipeline and runs it as a cron-safe script.

**Tech Stack:** Python 3.11+, `requests`, `astral`, `python-dotenv`, `pyyaml`, `pytest`

---

## Chunk 1: Scaffolding + color_utils.py

### Task 1: Project scaffolding

**Files:**
- Create: `.gitignore`
- Create: `.env.example`
- Create: `.env`
- Create: `requirements.txt`
- Create: `config.yaml`
- Create: `lights_config.json`
- Create: `src/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create .gitignore**

```
.env
*.pyc
__pycache__/
*.egg-info/
.DS_Store
tokens.json
lights_config.json
*.log
```

- [ ] **Step 2: Create .env.example**

```
OWM_API_KEY=your_openweathermap_api_key_here
HUE_CLIENT_ID=your_hue_client_id_here
HUE_CLIENT_SECRET=your_hue_client_secret_here
HUE_REFRESH_TOKEN=your_hue_refresh_token_here
```

- [ ] **Step 3: Create .env** (user fills in real values)

```
OWM_API_KEY=
HUE_CLIENT_ID=
HUE_CLIENT_SECRET=
HUE_REFRESH_TOKEN=
```

- [ ] **Step 4: Create requirements.txt**

```
requests>=2.31.0
astral>=3.2
python-dotenv>=1.0.0
pyyaml>=6.0.1
pytest>=7.4.0
```

- [ ] **Step 5: Create config.yaml**

```yaml
location:
  latitude: 49.3200
  longitude: -123.0724
  timezone: America/Vancouver

schedule:
  interval_minutes: 15
  transition_seconds: 60

api_keys:
  openweathermap: ${OWM_API_KEY}

hue:
  client_id: ${HUE_CLIENT_ID}
  client_secret: ${HUE_CLIENT_SECRET}
  refresh_token: ${HUE_REFRESH_TOKEN}

palette:
  brightness_multiplier: 1.0
  saturation_multiplier: 1.0
  cloud_desaturation_strength: 0.25
  rain_hue_shift: 15
  temperature_influence: 0.1
```

- [ ] **Step 6: Create src/__init__.py and tests/__init__.py** (empty files)

- [ ] **Step 7: Install dependencies**

Run: `pip install -r requirements.txt`
Expected: All packages install successfully

---

### Task 2: color_utils.py — HSB ↔ RGB ↔ CIE xy conversions

**Files:**
- Create: `src/color_utils.py`
- Create: `tests/test_color_utils.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_color_utils.py
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
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `pytest tests/test_color_utils.py -v`
Expected: ImportError or AttributeError — module doesn't exist yet

- [ ] **Step 3: Implement color_utils.py**

```python
# src/color_utils.py
"""
Color space conversion utilities.
HSB (Hue 0-360, Sat 0-100, Bri 0-100) → RGB (0-255) → CIE xy
Also: HSB → Hue API native values (hue 0-65535, sat 0-254, bri 1-254)
"""
import math


def hsb_to_rgb(hue_deg: float, sat_pct: float, bri_pct: float) -> tuple[int, int, int]:
    """Convert HSB (H:0-360, S:0-100, B:0-100) to RGB (0-255 each)."""
    h = hue_deg % 360
    s = sat_pct / 100.0
    v = bri_pct / 100.0

    if s == 0:
        c = int(v * 255)
        return c, c, c

    h_sector = h / 60.0
    i = int(h_sector)
    f = h_sector - i
    p = v * (1 - s)
    q = v * (1 - s * f)
    t = v * (1 - s * (1 - f))

    sectors = [
        (v, t, p), (q, v, p), (p, v, t),
        (p, q, v), (t, p, v), (v, p, q),
    ]
    r, g, b = sectors[i % 6]
    return int(r * 255), int(g * 255), int(b * 255)


def _linearize(c: float) -> float:
    """sRGB gamma to linear."""
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def rgb_to_xy(r: int, g: int, b: int) -> tuple[float, float]:
    """Convert RGB (0-255) to CIE xy chromaticity (Philips Hue wide gamut)."""
    r_lin = _linearize(r / 255.0)
    g_lin = _linearize(g / 255.0)
    b_lin = _linearize(b / 255.0)

    # Wide color gamut D65
    X = r_lin * 0.664511 + g_lin * 0.154324 + b_lin * 0.162028
    Y = r_lin * 0.283881 + g_lin * 0.668433 + b_lin * 0.047685
    Z = r_lin * 0.000088 + g_lin * 0.072310 + b_lin * 0.986039

    total = X + Y + Z
    if total == 0:
        return 0.0, 0.0
    return round(X / total, 4), round(Y / total, 4)


def hsb_to_hue_api(hue_deg: float, sat_pct: float, bri_pct: float) -> tuple[int, int, int]:
    """Convert HSB to Hue API native integers: hue (0-65535), sat (0-254), bri (1-254)."""
    hue_val = int((hue_deg % 360) / 360.0 * 65535)
    sat_val = int(min(sat_pct, 100) / 100.0 * 254)
    bri_val = max(1, int(min(bri_pct, 100) / 100.0 * 254))
    return hue_val, sat_val, bri_val
```

- [ ] **Step 4: Run tests to confirm they pass**

Run: `pytest tests/test_color_utils.py -v`
Expected: All 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/color_utils.py tests/test_color_utils.py src/__init__.py tests/__init__.py
git commit -m "feat: add color space conversion utilities (HSB→RGB→CIE xy, HSB→Hue API)"
```

---

## Chunk 2: environment.py

### Task 3: EnvironmentState dataclass + sun position

**Files:**
- Create: `src/environment.py`
- Create: `tests/test_environment.py`

- [ ] **Step 1: Write failing tests for sun position calculation**

```python
# tests/test_environment.py
import pytest
from datetime import datetime, timezone
import zoneinfo
from src.environment import get_sun_position, EnvironmentState

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
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `pytest tests/test_environment.py::TestSunPosition -v`
Expected: ImportError

- [ ] **Step 3: Implement EnvironmentState dataclass and get_sun_position**

```python
# src/environment.py
"""
Gather all environmental inputs: sun position + OpenWeatherMap weather data.
Returns EnvironmentState dataclass ready for the palette engine.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
import zoneinfo

import requests
from astral import LocationInfo
from astral.sun import sun, elevation, azimuth

logger = logging.getLogger(__name__)


@dataclass
class EnvironmentState:
    # Sun
    sun_elevation: float          # degrees, -90 to +90
    sun_azimuth: float            # degrees, 0-360
    # Weather
    condition: str                 # e.g. "Clear", "Rain", "Snow", "Fog", "Clouds"
    condition_id: int             # OWM weather condition code
    cloud_cover: float            # 0-100 %
    temperature_c: float          # Celsius
    humidity: float               # 0-100 %
    visibility_m: float           # metres (max 10000)
    wind_speed_ms: float          # m/s
    # Derived
    is_rain: bool = False
    is_snow: bool = False
    is_fog: bool = False
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def get_sun_position(dt: datetime, lat: float = 49.3200, lon: float = -123.0724) -> tuple[float, float]:
    """Return (elevation_degrees, azimuth_degrees) for given datetime and location."""
    loc = LocationInfo(latitude=lat, longitude=lon)
    elev = elevation(loc.observer, dt)
    azim = azimuth(loc.observer, dt)
    return round(float(elev), 2), round(float(azim), 2)


def fetch_weather(api_key: str, lat: float = 49.3200, lon: float = -123.0724) -> dict:
    """Fetch current weather from OpenWeatherMap. Returns raw JSON."""
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"lat": lat, "lon": lon, "appid": api_key, "units": "metric"}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def parse_weather(data: dict) -> dict:
    """Extract the fields we care about from OWM response."""
    weather = data["weather"][0]
    condition_id = weather["id"]
    return {
        "condition": weather["main"],
        "condition_id": condition_id,
        "cloud_cover": float(data.get("clouds", {}).get("all", 0)),
        "temperature_c": float(data["main"]["temp"]),
        "humidity": float(data["main"]["humidity"]),
        "visibility_m": float(data.get("visibility", 10000)),
        "wind_speed_ms": float(data.get("wind", {}).get("speed", 0)),
        "is_rain": 200 <= condition_id < 700,
        "is_snow": 600 <= condition_id < 700,
        "is_fog": 700 <= condition_id < 800,
    }


def get_environment(api_key: str, lat: float = 49.3200, lon: float = -123.0724) -> EnvironmentState:
    """Fetch all environment data and return an EnvironmentState."""
    now = datetime.now(zoneinfo.ZoneInfo("America/Vancouver"))
    elev, azim = get_sun_position(now, lat, lon)

    weather_data = fetch_weather(api_key, lat, lon)
    w = parse_weather(weather_data)

    state = EnvironmentState(
        sun_elevation=elev,
        sun_azimuth=azim,
        **w,
        timestamp=now,
    )
    logger.info(
        "Environment: elev=%.1f° clouds=%d%% condition=%s temp=%.1f°C",
        state.sun_elevation, state.cloud_cover, state.condition, state.temperature_c
    )
    return state
```

- [ ] **Step 4: Run sun position tests**

Run: `pytest tests/test_environment.py::TestSunPosition -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Write parse_weather tests (no API needed)**

Add to `tests/test_environment.py`:

```python
from src.environment import parse_weather

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
```

- [ ] **Step 6: Run all environment tests**

Run: `pytest tests/test_environment.py -v`
Expected: All 8 tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/environment.py tests/test_environment.py
git commit -m "feat: add environment data module with sun position and OWM weather parsing"
```

---

## Chunk 3: palette.py + preview.py

### Task 4: Palette engine — base curve

**Files:**
- Create: `src/palette.py`
- Create: `tests/test_palette.py`

The palette engine has two parts: (a) the base sun-elevation curve, and (b) weather modifiers that adjust it. Build and test them separately.

- [ ] **Step 1: Write failing tests for base curve**

```python
# tests/test_palette.py
import pytest
from src.palette import (
    cosine_interpolate,
    get_base_hsb,
    apply_weather_modifiers,
    compute_hsb,
)
from src.environment import EnvironmentState
from datetime import datetime, timezone

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

    def test_at_midpoint_not_linear(self):
        # Cosine interp at t=0.5 should equal 5.0 (symmetric at midpoint)
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
        assert 20 <= s <= 35
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
        clear_state = make_state(30, clouds=0)
        cloudy_state = make_state(30, clouds=100)
        _, s_clear, _ = get_base_hsb(30)
        h, s_cloudy, b = apply_weather_modifiers(get_base_hsb(30), cloudy_state, {
            "cloud_desaturation_strength": 0.25,
            "rain_hue_shift": 15,
            "temperature_influence": 0.1,
        })
        assert s_cloudy < s_clear

    def test_rain_shifts_hue_blue(self):
        rain_state = make_state(30, clouds=80, condition="Rain", cid=501, is_rain=True)
        h_base, _, _ = get_base_hsb(30)
        h_rain, _, _ = apply_weather_modifiers(get_base_hsb(30), rain_state, {
            "cloud_desaturation_strength": 0.25,
            "rain_hue_shift": 15,
            "temperature_influence": 0.1,
        })
        # Rain shifts toward blue (higher hue or wraps)
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
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `pytest tests/test_palette.py -v`
Expected: ImportError

- [ ] **Step 3: Implement palette.py**

```python
# src/palette.py
"""
Palette engine: maps EnvironmentState → HSB color values.

Base curve: sun elevation angle drives color through anchor points with
cosine interpolation. Weather modifiers shift/scale the result.
"""
import math
import logging
from src.environment import EnvironmentState

logger = logging.getLogger(__name__)

# Base curve anchor points: (sun_elevation_degrees, hue, saturation, brightness)
# Elevation values must be sorted ascending.
ANCHOR_POINTS = [
    (-25, 250, 65, 10),   # Deep night: deep indigo
    (-12, 270, 58, 20),   # Twilight: violet/lavender
    (-3,  30,  78, 37),   # Dawn/dusk: amber/coral
    (5,   35,  68, 60),   # Golden hour: warm amber/peach
    (20,  42,  38, 77),   # Morning/afternoon: warm white
    (45,  50,  27, 92),   # Midday: neutral/cool white
]


def cosine_interpolate(a: float, b: float, t: float) -> float:
    """Cosine interpolation between a and b at position t (0-1)."""
    t2 = (1 - math.cos(t * math.pi)) / 2
    return a * (1 - t2) + b * t2


def _interpolate_anchors(elevation: float) -> tuple[float, float, float]:
    """Find the two surrounding anchor points and cosine-interpolate between them."""
    if elevation <= ANCHOR_POINTS[0][0]:
        return float(ANCHOR_POINTS[0][1]), float(ANCHOR_POINTS[0][2]), float(ANCHOR_POINTS[0][3])
    if elevation >= ANCHOR_POINTS[-1][0]:
        return float(ANCHOR_POINTS[-1][1]), float(ANCHOR_POINTS[-1][2]), float(ANCHOR_POINTS[-1][3])

    for i in range(len(ANCHOR_POINTS) - 1):
        e0, h0, s0, b0 = ANCHOR_POINTS[i]
        e1, h1, s1, b1 = ANCHOR_POINTS[i + 1]
        if e0 <= elevation <= e1:
            t = (elevation - e0) / (e1 - e0)
            return (
                cosine_interpolate(h0, h1, t),
                cosine_interpolate(s0, s1, t),
                cosine_interpolate(b0, b1, t),
            )
    return float(ANCHOR_POINTS[-1][1]), float(ANCHOR_POINTS[-1][2]), float(ANCHOR_POINTS[-1][3])


def get_base_hsb(elevation: float) -> tuple[float, float, float]:
    """Return base HSB for a given sun elevation angle."""
    return _interpolate_anchors(elevation)


def apply_weather_modifiers(
    base_hsb: tuple[float, float, float],
    state: EnvironmentState,
    config: dict,
) -> tuple[float, float, float]:
    """
    Apply weather modifiers to base HSB. All adjustments are additive/multiplicative
    on top of the base — never replacements.
    """
    h, s, b = base_hsb
    cloud_strength = config.get("cloud_desaturation_strength", 0.25)
    rain_hue_shift = config.get("rain_hue_shift", 15)
    temp_influence = config.get("temperature_influence", 0.1)

    # Cloud cover: desaturate + slight brightness drop + cool hue shift
    cloud_factor = state.cloud_cover / 100.0
    s -= cloud_factor * cloud_strength * 100  # up to -25 sat at full overcast
    b -= cloud_factor * 8                     # slight brightness drop
    h += cloud_factor * 5                     # slight cool shift

    # Rain: shift toward blue-grey, drop brightness
    if state.is_rain and not state.is_snow:
        rain_intensity = min(state.cloud_cover / 100.0, 1.0)
        h += rain_hue_shift * rain_intensity
        b -= 20 * rain_intensity
        s -= 10 * rain_intensity

    # Snow: cool lavender tint, slight brightness boost (reflective), desaturate
    if state.is_snow:
        h += 10  # lavender shift
        b += 5   # reflective boost
        s -= 20

    # Fog: muted warm grey, significant desaturation
    if state.is_fog:
        fog_factor = max(0, 1 - (state.visibility_m / 10000))
        s -= fog_factor * 30
        b -= fog_factor * 10
        h = h * (1 - fog_factor * 0.3) + 35 * (fog_factor * 0.3)  # nudge toward warm grey

    # Temperature: very subtle warm/cool nudge
    # 15°C = neutral; colder nudges cool (+hue), warmer nudges warm (-hue)
    temp_delta = (15.0 - state.temperature_c) * temp_influence
    h += temp_delta * 0.5  # very subtle — max ±5° hue at 10°C deviation

    # Clamp all values
    h = h % 360
    s = max(0.0, min(100.0, s))
    b = max(0.0, min(100.0, b))

    return h, s, b


def compute_hsb(
    state: EnvironmentState,
    palette_config: dict | None = None,
    brightness_multiplier: float = 1.0,
    saturation_multiplier: float = 1.0,
) -> tuple[float, float, float]:
    """
    Full pipeline: EnvironmentState → HSB ready for the Hue API.
    palette_config keys: cloud_desaturation_strength, rain_hue_shift, temperature_influence
    """
    if palette_config is None:
        palette_config = {
            "cloud_desaturation_strength": 0.25,
            "rain_hue_shift": 15,
            "temperature_influence": 0.1,
        }

    base = get_base_hsb(state.sun_elevation)
    h, s, b = apply_weather_modifiers(base, state, palette_config)

    # Apply global multipliers from config
    s = max(0.0, min(100.0, s * saturation_multiplier))
    b = max(1.0, min(100.0, b * brightness_multiplier))

    logger.info(
        "Palette: elev=%.1f° → base H=%.0f S=%.0f B=%.0f → final H=%.0f S=%.0f B=%.0f",
        state.sun_elevation, base[0], base[1], base[2], h, s, b
    )
    return round(h, 1), round(s, 1), round(b, 1)
```

- [ ] **Step 4: Run palette tests**

Run: `pytest tests/test_palette.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/palette.py tests/test_palette.py
git commit -m "feat: add palette engine with sun-elevation curve and weather modifiers"
```

---

### Task 5: preview.py — CLI testing tool

**Files:**
- Create: `preview.py`

- [ ] **Step 1: Implement preview.py**

```python
#!/usr/bin/env python3
"""
Preview what colors the palette would generate for any datetime/weather combo.

Usage:
  python preview.py
  python preview.py --time "2025-06-21 12:00" --clouds 80 --condition rain
  python preview.py --time "2025-12-21 16:30" --clouds 30 --temp -2
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path
import zoneinfo

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from src.environment import EnvironmentState, get_sun_position
from src.palette import compute_hsb
from src.color_utils import hsb_to_rgb

VANCOUVER_TZ = zoneinfo.ZoneInfo("America/Vancouver")

CONDITION_MAP = {
    "clear": ("Clear", 800),
    "clouds": ("Clouds", 801),
    "rain": ("Rain", 501),
    "snow": ("Snow", 601),
    "fog": ("Fog", 741),
    "mist": ("Mist", 701),
    "drizzle": ("Drizzle", 300),
    "thunderstorm": ("Thunderstorm", 200),
}

def color_block(r: int, g: int, b: int) -> str:
    """Return a terminal color block using ANSI escape codes."""
    return f"\033[48;2;{r};{g};{b}m     \033[0m"

def main():
    parser = argparse.ArgumentParser(description="Preview Hue ambient light colors")
    parser.add_argument("--time", default=None,
                        help='Datetime in "YYYY-MM-DD HH:MM" format (default: now)')
    parser.add_argument("--clouds", type=float, default=0, help="Cloud cover 0-100")
    parser.add_argument("--condition", default="clear",
                        choices=list(CONDITION_MAP.keys()), help="Weather condition")
    parser.add_argument("--temp", type=float, default=15.0, help="Temperature in Celsius")
    parser.add_argument("--humidity", type=float, default=60.0)
    parser.add_argument("--wind", type=float, default=2.0, help="Wind speed m/s")
    parser.add_argument("--visibility", type=float, default=10000.0, help="Visibility in metres")
    parser.add_argument("--bri-mult", type=float, default=1.0, help="Brightness multiplier")
    parser.add_argument("--sat-mult", type=float, default=1.0, help="Saturation multiplier")
    args = parser.parse_args()

    if args.time:
        dt = datetime.strptime(args.time, "%Y-%m-%d %H:%M").replace(tzinfo=VANCOUVER_TZ)
    else:
        dt = datetime.now(VANCOUVER_TZ)

    elev, azim = get_sun_position(dt)
    condition_name, condition_id = CONDITION_MAP[args.condition]
    is_rain = 200 <= condition_id < 700
    is_snow = 600 <= condition_id < 700
    is_fog = 700 <= condition_id < 800

    state = EnvironmentState(
        sun_elevation=elev, sun_azimuth=azim,
        condition=condition_name, condition_id=condition_id,
        cloud_cover=args.clouds, temperature_c=args.temp,
        humidity=args.humidity, visibility_m=args.visibility,
        wind_speed_ms=args.wind, is_rain=is_rain, is_snow=is_snow, is_fog=is_fog,
        timestamp=dt,
    )

    palette_config = {
        "cloud_desaturation_strength": 0.25,
        "rain_hue_shift": 15,
        "temperature_influence": 0.1,
    }

    h, s, b = compute_hsb(state, palette_config,
                           brightness_multiplier=args.bri_mult,
                           saturation_multiplier=args.sat_mult)
    r, g, b_val = hsb_to_rgb(h, s, b)

    print(f"\nPreview for: {dt.strftime('%Y-%m-%d %H:%M %Z')}")
    print(f"  Sun elevation : {elev:+.1f}°  azimuth: {azim:.0f}°")
    print(f"  Condition     : {condition_name}  clouds: {args.clouds:.0f}%  temp: {args.temp:.1f}°C")
    print(f"\n  HSB           : H={h:.0f}°  S={s:.0f}%  B={b:.0f}%")
    print(f"  RGB           : ({r}, {g}, {b_val})")
    print(f"  Color block   : {color_block(r, g, b_val)}\n")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test preview manually**

Run: `python preview.py --time "2025-06-21 12:00" --clouds 0 --condition clear`
Expected: Output showing warm/bright colors with high B%

Run: `python preview.py --time "2025-12-21 16:30" --clouds 80 --condition rain`
Expected: Output showing cooler, desaturated, darker colors

- [ ] **Step 3: Commit**

```bash
git add preview.py
git commit -m "feat: add preview CLI tool for palette testing without real API calls"
```

---

## Chunk 4: hue_api.py + setup_hue.py

### Task 6: Hue API module

**Files:**
- Create: `src/hue_api.py`
- Create: `tests/test_hue_api.py`

- [ ] **Step 1: Write unit tests for token management and color conversion (no live API)**

```python
# tests/test_hue_api.py
import pytest
import json
import os
import tempfile
from unittest.mock import patch, MagicMock
from src.hue_api import (
    save_tokens, load_tokens,
    build_light_state,
    HueClient,
)

class TestTokenStorage:
    def test_save_and_load_roundtrip(self, tmp_path):
        tokens_file = tmp_path / "tokens.json"
        save_tokens("acc123", "ref456", str(tokens_file))
        data = load_tokens(str(tokens_file))
        assert data["access_token"] == "acc123"
        assert data["refresh_token"] == "ref456"

    def test_load_missing_returns_none(self, tmp_path):
        data = load_tokens(str(tmp_path / "nonexistent.json"))
        assert data is None

class TestBuildLightState:
    def test_returns_required_keys(self):
        state = build_light_state(35, 70, 80, transition_seconds=60)
        assert "hue" in state
        assert "sat" in state
        assert "bri" in state
        assert "transitiontime" in state
        assert state["on"] is True

    def test_transition_time_in_deciseconds(self):
        state = build_light_state(35, 70, 80, transition_seconds=60)
        assert state["transitiontime"] == 600  # 60s * 10

    def test_hue_range(self):
        state = build_light_state(0, 0, 100)
        assert 0 <= state["hue"] <= 65535

    def test_brightness_min_1(self):
        state = build_light_state(0, 0, 0)
        assert state["bri"] >= 1
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `pytest tests/test_hue_api.py -v`
Expected: ImportError

- [ ] **Step 3: Implement hue_api.py**

```python
# src/hue_api.py
"""
Philips Hue Remote API client.

Token flow:
  1. Initial tokens obtained via setup_hue.py OAuth flow
  2. Access token stored in tokens.json (expires in 7 days)
  3. Refresh token used to get new access token when expired
  4. Updated tokens saved back to tokens.json
"""
import json
import logging
import time
from pathlib import Path
from typing import Optional

import requests

from src.color_utils import hsb_to_hue_api

logger = logging.getLogger(__name__)

TOKENS_FILE = "tokens.json"
HUE_API_BASE = "https://api.meethue.com"


def save_tokens(access_token: str, refresh_token: str, path: str = TOKENS_FILE) -> None:
    """Persist tokens to JSON file."""
    with open(path, "w") as f:
        json.dump({
            "access_token": access_token,
            "refresh_token": refresh_token,
            "saved_at": time.time(),
        }, f, indent=2)


def load_tokens(path: str = TOKENS_FILE) -> Optional[dict]:
    """Load tokens from JSON file. Returns None if file doesn't exist."""
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> dict:
    """Use refresh token to get a new access token. Returns new token dict."""
    resp = requests.post(
        f"{HUE_API_BASE}/v2/oauth2/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        auth=(client_id, client_secret),
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    return {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token", refresh_token),
    }


def build_light_state(
    hue_deg: float, sat_pct: float, bri_pct: float, transition_seconds: int = 60
) -> dict:
    """Build the Hue API light state dict from HSB values."""
    hue_val, sat_val, bri_val = hsb_to_hue_api(hue_deg, sat_pct, bri_pct)
    return {
        "on": True,
        "hue": hue_val,
        "sat": sat_val,
        "bri": bri_val,
        "transitiontime": transition_seconds * 10,  # deciseconds
    }


class HueClient:
    """Client for the Philips Hue Remote API."""

    def __init__(self, client_id: str, client_secret: str, tokens_file: str = TOKENS_FILE):
        self.client_id = client_id
        self.client_secret = client_secret
        self.tokens_file = tokens_file
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._bridge_username: Optional[str] = None
        self._load_tokens()

    def _load_tokens(self) -> None:
        data = load_tokens(self.tokens_file)
        if data:
            self._access_token = data["access_token"]
            self._refresh_token = data["refresh_token"]
            self._bridge_username = data.get("bridge_username")

    def _ensure_token(self) -> None:
        """Refresh access token if needed."""
        if not self._refresh_token:
            raise RuntimeError("No refresh token. Run setup_hue.py first.")
        try:
            new_tokens = refresh_access_token(
                self.client_id, self.client_secret, self._refresh_token
            )
            self._access_token = new_tokens["access_token"]
            self._refresh_token = new_tokens["refresh_token"]
            tokens_data = load_tokens(self.tokens_file) or {}
            save_tokens(
                self._access_token,
                self._refresh_token,
                self.tokens_file,
            )
            logger.info("Access token refreshed successfully")
        except Exception as e:
            logger.error("Failed to refresh token: %s", e)
            raise

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

    def _api_url(self, path: str) -> str:
        return f"{HUE_API_BASE}/bridge/{self._bridge_username}/{path}"

    def _request(self, method: str, path: str, **kwargs) -> dict:
        """Make an API request, refreshing token on 401."""
        url = self._api_url(path)
        resp = requests.request(method, url, headers=self._headers(), timeout=10, **kwargs)
        if resp.status_code == 401:
            logger.info("Token expired, refreshing...")
            self._ensure_token()
            resp = requests.request(method, url, headers=self._headers(), timeout=10, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def get_lights(self) -> dict:
        """Return all lights from the bridge."""
        return self._request("GET", "lights")

    def set_light_state(self, light_id: str, state: dict) -> None:
        """Push a state dict to a single light."""
        self._request("PUT", f"lights/{light_id}/state", json=state)
        logger.debug("Light %s updated: %s", light_id, state)

    def set_all_lights(
        self,
        light_ids: list[str],
        hue_deg: float,
        sat_pct: float,
        bri_pct: float,
        transition_seconds: int = 60,
    ) -> None:
        """Push HSB values to all configured lights."""
        state = build_light_state(hue_deg, sat_pct, bri_pct, transition_seconds)
        errors = []
        for light_id in light_ids:
            try:
                self.set_light_state(light_id, state)
            except Exception as e:
                logger.error("Failed to update light %s: %s", light_id, e)
                errors.append(light_id)
        if errors:
            logger.warning("Failed to update lights: %s", errors)
        else:
            logger.info(
                "Updated %d light(s): H=%.0f° S=%.0f%% B=%.0f%%",
                len(light_ids), hue_deg, sat_pct, bri_pct
            )
```

- [ ] **Step 4: Run hue_api unit tests**

Run: `pytest tests/test_hue_api.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/hue_api.py tests/test_hue_api.py
git commit -m "feat: add Hue Remote API client with token management and light control"
```

---

### Task 7: setup_hue.py — OAuth flow and light discovery

**Files:**
- Create: `setup_hue.py`

- [ ] **Step 1: Implement setup_hue.py**

```python
#!/usr/bin/env python3
"""
One-time setup: Philips Hue OAuth flow + light discovery.

Run this once to authorize the app and discover which lights to control.
Saves tokens to tokens.json and light config to lights_config.json.

Usage:
  python setup_hue.py
"""
import json
import sys
import webbrowser
from pathlib import Path
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv
import os

load_dotenv()

HUE_API_BASE = "https://api.meethue.com"
TOKENS_FILE = "tokens.json"
LIGHTS_CONFIG_FILE = "lights_config.json"


def get_oauth_url(client_id: str, state: str = "setup") -> str:
    params = urlencode({
        "clientid": client_id,
        "response_type": "code",
        "state": state,
        "appid": "hue_ambient",
        "deviceid": "pythonanywhere",
        "devicename": "HueAmbient",
    })
    return f"{HUE_API_BASE}/v2/oauth2/authorize?{params}"


def exchange_code_for_tokens(client_id: str, client_secret: str, code: str) -> dict:
    resp = requests.post(
        f"{HUE_API_BASE}/v2/oauth2/token",
        data={"grant_type": "authorization_code", "code": code},
        auth=(client_id, client_secret),
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def create_bridge_user(access_token: str) -> str:
    """Create a whitelisted user on the bridge and return the username."""
    resp = requests.post(
        f"{HUE_API_BASE}/bridge",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json={"devicetype": "hue_ambient#pythonanywhere", "generateclientkey": True},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, list) and "success" in data[0]:
        return data[0]["success"]["username"]
    raise RuntimeError(f"Unexpected response creating bridge user: {data}")


def discover_lights(access_token: str, bridge_username: str) -> dict:
    """Return all lights from the bridge."""
    resp = requests.get(
        f"{HUE_API_BASE}/bridge/{bridge_username}/lights",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def main():
    client_id = os.getenv("HUE_CLIENT_ID")
    client_secret = os.getenv("HUE_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("ERROR: HUE_CLIENT_ID and HUE_CLIENT_SECRET must be set in .env")
        sys.exit(1)

    print("\n=== Philips Hue Setup ===\n")
    print("Step 1: Authorize the app")
    url = get_oauth_url(client_id)
    print(f"\nOpening authorization URL in browser:\n{url}\n")
    webbrowser.open(url)

    print("After authorizing, you'll be redirected to a URL like:")
    print("  https://your-callback-url?code=XXXX&state=setup")
    code = input("\nPaste the 'code' parameter from the redirect URL: ").strip()

    print("\nStep 2: Exchanging code for tokens...")
    token_data = exchange_code_for_tokens(client_id, client_secret, code)
    access_token = token_data["access_token"]
    refresh_token = token_data["refresh_token"]

    print("\nStep 3: Creating bridge user...")
    bridge_username = create_bridge_user(access_token)
    print(f"Bridge username: {bridge_username}")

    print("\nStep 4: Discovering lights...")
    lights = discover_lights(access_token, bridge_username)

    print("\nFound lights:")
    for lid, info in lights.items():
        print(f"  [{lid}] {info['name']} — type: {info['type']}")

    selected = input("\nEnter light IDs to control (comma-separated, e.g. 1,2,3): ").strip()
    light_ids = [s.strip() for s in selected.split(",") if s.strip()]

    # Save tokens
    tokens_data = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "bridge_username": bridge_username,
        "saved_at": __import__("time").time(),
    }
    with open(TOKENS_FILE, "w") as f:
        json.dump(tokens_data, f, indent=2)
    print(f"\nTokens saved to {TOKENS_FILE}")

    # Save lights config
    lights_config = {
        "light_ids": light_ids,
        "bridge_username": bridge_username,
        "lights_info": {lid: {"name": lights[lid]["name"]} for lid in light_ids if lid in lights},
    }
    with open(LIGHTS_CONFIG_FILE, "w") as f:
        json.dump(lights_config, f, indent=2)
    print(f"Light config saved to {LIGHTS_CONFIG_FILE}")

    print("\n=== Setup complete! ===")
    print("You can now run: python src/main.py")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add setup_hue.py
git commit -m "feat: add one-time Hue OAuth setup and light discovery script"
```

---

## Chunk 5: main.py + final wiring

### Task 8: main.py — full pipeline runner

**Files:**
- Create: `src/main.py`

- [ ] **Step 1: Implement main.py**

```python
#!/usr/bin/env python3
"""
Main entry point. Fetches environment data, computes palette, pushes to Hue.
Designed to be run every 15 minutes via PythonAnywhere cron.
"""
import json
import logging
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Ensure project root is on path when run directly
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.environment import get_environment, EnvironmentState
from src.palette import compute_hsb
from src.hue_api import HueClient

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")

CONFIG_FILE = Path(__file__).parent.parent / "config.yaml"
LIGHTS_CONFIG_FILE = Path(__file__).parent.parent / "lights_config.json"
TOKENS_FILE = Path(__file__).parent.parent / "tokens.json"


def load_config(path: Path) -> dict:
    """Load config.yaml, resolving ${VAR} references from environment."""
    with open(path) as f:
        raw = f.read()
    # Resolve ${VAR} references
    import re
    def replace_var(m):
        return os.getenv(m.group(1), m.group(0))
    raw = re.sub(r'\$\{(\w+)\}', replace_var, raw)
    return yaml.safe_load(raw)


def load_lights_config(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def run(config: dict, lights_config: dict) -> None:
    owm_key = config["api_keys"]["openweathermap"]
    lat = config["location"]["latitude"]
    lon = config["location"]["longitude"]
    transition_s = config["schedule"]["transition_seconds"]
    palette_cfg = config.get("palette", {})
    bri_mult = palette_cfg.get("brightness_multiplier", 1.0)
    sat_mult = palette_cfg.get("saturation_multiplier", 1.0)

    # 1. Fetch environment
    try:
        state = get_environment(owm_key, lat, lon)
    except Exception as e:
        logger.error("Failed to fetch environment data: %s — skipping cycle", e)
        return

    # 2. Compute palette
    h, s, b = compute_hsb(
        state,
        palette_config={
            "cloud_desaturation_strength": palette_cfg.get("cloud_desaturation_strength", 0.25),
            "rain_hue_shift": palette_cfg.get("rain_hue_shift", 15),
            "temperature_influence": palette_cfg.get("temperature_influence", 0.1),
        },
        brightness_multiplier=bri_mult,
        saturation_multiplier=sat_mult,
    )

    # 3. Push to Hue
    hue_cfg = config["hue"]
    client = HueClient(
        client_id=hue_cfg["client_id"],
        client_secret=hue_cfg["client_secret"],
        tokens_file=str(TOKENS_FILE),
    )

    light_ids = lights_config["light_ids"]
    try:
        client.set_all_lights(light_ids, h, s, b, transition_seconds=transition_s)
    except Exception as e:
        logger.error("Failed to update Hue lights: %s — will retry next cycle", e)
        # Retry once
        try:
            client.set_all_lights(light_ids, h, s, b, transition_seconds=transition_s)
        except Exception as e2:
            logger.error("Retry also failed: %s — skipping cycle", e2)
            return

    logger.info(
        "Cycle complete: elev=%.1f° cond=%s → H=%.0f S=%.0f B=%.0f → %d light(s)",
        state.sun_elevation, state.condition, h, s, b, len(light_ids)
    )


def main():
    try:
        config = load_config(CONFIG_FILE)
    except FileNotFoundError:
        logger.error("config.yaml not found at %s", CONFIG_FILE)
        sys.exit(1)

    try:
        lights_config = load_lights_config(LIGHTS_CONFIG_FILE)
    except FileNotFoundError:
        logger.error("lights_config.json not found. Run setup_hue.py first.")
        sys.exit(1)

    run(config, lights_config)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add src/main.py
git commit -m "feat: add main pipeline runner with graceful error handling and retry logic"
```

---

### Task 9: Verify full test suite passes

- [ ] **Step 1: Run all tests**

Run: `pytest tests/ -v`
Expected: All tests PASS with no errors

- [ ] **Step 2: Run a preview to confirm pipeline**

Run: `python preview.py --time "2025-06-21 20:00" --clouds 20 --condition clear`
Expected: Warm golden-hour colors (H ~30-40, S ~60-70, B ~60-70)

Run: `python preview.py --time "2025-01-15 02:00" --clouds 100 --condition rain`
Expected: Dark, cool, desaturated (H ~220-240, S ~20-35, B ~5-15)

- [ ] **Step 3: Final commit**

```bash
git add .
git commit -m "chore: finalize project structure and scaffolding"
```

---

## Deployment Checklist (PythonAnywhere)

After all above tasks complete:

1. Upload project directory to PythonAnywhere (`~/hue-ambient/`)
2. Create `.env` with real API keys and tokens
3. `pip install -r requirements.txt`
4. Run `python setup_hue.py` to complete OAuth and get `tokens.json` + `lights_config.json`
5. Test manually: `python src/main.py`
6. Add scheduled task: `python /home/yourusername/hue-ambient/src/main.py` every 15 minutes
