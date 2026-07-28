# Hue Ambient Light Sync

## Project Overview

A Python application that automatically adjusts Philips Hue smart lights to artistically complement the outdoor environment in North Vancouver, BC. Rather than literally mirroring outside colors, the system creates an ambient indoor atmosphere that *responds to* outdoor conditions — shifting fluidly throughout the day and across weather patterns.

The script runs on a schedule (every 15 minutes) via PythonAnywhere's free tier, communicates with the Hue bridge through the Hue Remote (cloud) API, and pulls weather data from OpenWeatherMap.

## Architecture

```
PythonAnywhere (cron every 15 min)
  → OpenWeatherMap API (weather + conditions)
  → Sun position calculation (astral library, for North Vancouver coords)
  → Palette engine (base curve + weather modifiers)
  → Hue Remote API (push colors to lights)
```

## Core Design Philosophy

**No rigid rules.** The system does NOT use a lookup table like "rain = blue lights." Instead, it uses a continuous color model:

1. A **base color curve** driven by sun elevation angle — the primary input that defines the arc of the day
2. **Weather modifiers** that shift hue, saturation, and brightness relative to the base curve
3. Smooth **interpolation** between anchor points so every moment produces a unique blend

The goal is that a cloudy January sunset feels completely different from a clear July sunset, and the lights reflect that naturally.

## Technical Components

### 1. Environment Data Module (`environment.py`)

Responsible for gathering all environmental inputs:

- **OpenWeatherMap API** (free tier): current weather condition, cloud cover %, temperature, humidity, visibility
- **Sun position** (use `astral` library): calculate sun elevation angle and azimuth for North Vancouver (lat: 49.3200, lon: -123.0724) at current time
- **Derived values**: time relative to sunrise/sunset, golden hour detection, twilight phase

Returns a single `EnvironmentState` dataclass with all values normalized and ready for the palette engine.

### 2. Palette Engine (`palette.py`)

The artistic core. Takes an `EnvironmentState` and outputs HSB (hue, saturation, brightness) values.

**Base color curve** — defined as anchor points mapped to sun elevation angles, with smooth interpolation between them:

| Sun Elevation | Phase | Hue | Saturation | Brightness |
|---|---|---|---|---|
| -25° | Deep night | 250° (indigo) | 70% | 8% |
| -14° | Twilight | 272° (violet) | 60% | 16% |
| -8° | Pre-dawn/dusk | 300° (mauve) | 48% | 24% |
| -4° | Horizon | 350° (deep coral) | 68% | 33% |
| 0° | Sunrise/sunset | 12° (coral-amber) | 82% | 44% |
| 8° | Golden hour | 22° (rich amber) | 80% | 63% |
| 18° | Morning/afternoon | 32° (gold) | 62% | 77% |
| 32° | Warm neutral | 44° | 40% | 87% |
| 46° | Cool gold | 62° | 14% | 92% |
| 51° | Crossover | 165° | 5% (near-white) | 96% |
| 64° | Summer midday | 195° (cool cyan-white) | 22% | 100% |

These values are starting points — they should be tunable via a config file.

Two constraints on this curve:

- **The day is an arc, not a band.** Hue travels the wheel rather than sitting
  in amber all day. Because the curve is driven by sun elevation and this
  latitude tops out near 17° in December, winter never reaches the cool end —
  a January afternoon stays amber while a July midday goes cyan-white. That
  seasonal split is the whole point, and it falls out of the physics for free.
- **No visible green.** The gold→cyan sweep has to cross the green band
  (roughly 70–160°), which looks wrong on an indoor light. Saturation is
  crushed to single digits across the 46–51° crossover so the transit reads as
  plain white. Any new saturation *boost* must therefore be multiplicative, not
  additive — an additive boost re-saturates the crossover straight back into
  green. `tests/test_palette.py::TestNoGreenLight` sweeps the whole elevation
  range against every weather condition to enforce this.

**Sun azimuth** breaks the symmetry of the day. Elevation alone is symmetric
about solar noon, so 9am and 3pm produced an identical colour; azimuth tells us
which side of noon we are on, and the afternoon is skewed warmer and slightly
more saturated to match how afternoon light actually reads.

**Weather modifiers** — each modifier adjusts the base curve output:

- **Cloud cover** (0-100%): Desaturates proportionally (up to -25% sat at full overcast), reduces brightness slightly. Deliberately *no* hue push — overcast removes colour rather than adding one, and nudging a warm hue "toward cool" only walks it into yellow-green.
- **Rain**: Drifts toward blue-grey (210-230°), drops brightness by 15-25%, adds a "weight" to the atmosphere. The hue drift is scaled by how desaturated the colour already is, so vivid colours grey out *before* they swing round the wheel.
- **Snow**: Adds lavender/cool white tint, increases brightness slightly (reflective quality), high saturation reduction
- **Fog**: Compresses the entire color range toward muted warm grey, significant saturation reduction, moderate brightness
- **Temperature**: Subtle global warm/cool shift — colder temps nudge hue slightly cooler, warmer temps nudge warmer. This should be very subtle, not dominant.
- **Wind**: Could optionally influence transition speed or add slight variability

Modifiers should be **multiplicative/additive adjustments** to the base HSB values, not replacements. They stack naturally.

**Interpolation**: Use cosine interpolation (not linear) between anchor points for smoother, more natural transitions.

**Hue blending**: never blend hue linearly — a linear blend from amber to violet
walks through the middle of the wheel and comes out teal. Use `blend_hue()` for
the short path around the circle, and `blend_hue_descending()` for bad-weather
targets. Warm hues sit almost exactly *opposite* blue-grey, so the "short" path
between them is a coin flip that half the time lands in green; forcing the
descending route (amber → red → magenta → violet → blue) keeps rain and storms
in the same family as the night end of the curve.

### 3. Hue API Module (`hue_api.py`)

Handles all communication with the Philips Hue Remote API:

- **Token management**: Store refresh token in `.env`, automatically refresh access token when expired. Save updated refresh tokens back to `.env` or a `tokens.json` file.
- **Light discovery**: On first run (or via a setup command), query the bridge for available lights and let the user configure which lights to control. Store config in `lights_config.json`.
- **Color conversion**: Hue uses CIE xy color space, not HSB. Include conversion functions (HSB → RGB → CIE xy). The Hue API also accepts `hue` (0-65535), `sat` (0-254), and `bri` (1-254) values directly, which may be simpler.
- **Transition time**: Hue supports `transitiontime` in deciseconds (10ths of a second). Use long transitions (e.g., 600 = 60 seconds) so lights fade smoothly rather than jumping between states. Since the script runs every 15 minutes, a 60-90 second transition feels natural.
- **Rate limiting**: Be respectful of API limits. Batch light updates where possible.

### 4. Configuration (`config.yaml`)

All tunable values in one place:

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

# Palette tuning - adjust these to taste
palette:
  brightness_multiplier: 1.0  # Global brightness scale (0.5 = half bright, 1.5 = brighter)
  saturation_multiplier: 1.0  # Global saturation scale
  brightness_floor: 60  # Brightness is compressed into this..100, not clamped
  cloud_desaturation_strength: 0.25  # How much clouds desaturate (0-1)
  rain_hue_target: 215  # Hue to drift toward during rain (blue-grey)
  temperature_influence: 0.1  # How much temp affects color (0 = none, 1 = heavy)
  azimuth_warmth: 0.10  # How much warmer afternoons run than mornings
  wind_influence: 0.15  # How much wind lifts saturation/brightness
```

**Brightness floor**: compressing 0-100 into `floor`-100 (rather than clamping
everything below the floor *to* the floor) is what keeps the night arc alive.
A hard clamp flattened deep night, twilight and dawn to one identical value.

### 5. Main Runner (`main.py`)

- Load config and environment variables
- Fetch environment state
- Run palette engine
- Push colors to Hue
- Log what happened (timestamp, conditions, resulting colors)
- Handle errors gracefully (if weather API is down, use last known state; if Hue API fails, retry once then skip)

### 6. Setup / Testing Utilities

- `setup.py` or CLI command: Walk through initial Hue OAuth flow, discover lights, create initial config
- `preview.py`: Given a datetime and weather override, show what colors would be generated (useful for tuning without waiting for real conditions)
- `test_connection.py`: Verify Hue API credentials and weather API key work

## Dependencies

```
requests
astral
python-dotenv
pyyaml
```

Keep dependencies minimal. No frameworks needed.

## File Structure

```
hue-ambient/
├── CLAUDE.md
├── .env                  # API keys and tokens (gitignored)
├── .env.example          # Template showing required env vars
├── .gitignore
├── config.yaml           # Tunable palette and location settings
├── lights_config.json    # Which lights to control (generated by setup)
├── requirements.txt
├── src/
│   ├── __init__.py
│   ├── main.py           # Entry point
│   ├── environment.py    # Weather + sun data fetching
│   ├── palette.py        # Color curve + modifier engine
│   ├── hue_api.py        # Hue Remote API communication
│   └── color_utils.py    # HSB/RGB/CIE conversion helpers
├── setup_hue.py          # One-time OAuth + light discovery
├── preview.py            # Test palette output for any datetime/weather
├── always_on.py          # PythonAnywhere always-on task wrapper (15-min loop)
└── tests/
    ├── test_palette.py   # Unit tests for color calculations
    └── test_environment.py
```

## Build Order

Build and test in this sequence:

1. **`color_utils.py`** — Pure math, no API calls. Write HSB ↔ RGB ↔ CIE xy conversions with unit tests. This is foundational and independently testable.

2. **`environment.py`** — Connect to OpenWeatherMap, integrate `astral` for sun position. Test with real API calls to confirm data shape. Create the `EnvironmentState` dataclass.

3. **`palette.py`** — The creative core. Implement the base curve with anchor points and cosine interpolation, then layer on weather modifiers. Test extensively with `preview.py` — feed it various datetime/weather combos and verify the outputs feel right artistically.

4. **`hue_api.py`** — Token management, light discovery, color pushing. Test with `test_connection.py` to confirm you can actually change a light.

5. **`main.py`** — Wire everything together. Run manually first, verify end-to-end, then deploy to PythonAnywhere cron.

6. **`preview.py`** — Build this alongside palette.py. It should accept CLI args like `--time "2025-01-15 16:30" --clouds 80 --condition rain` and print the resulting HSB values (and maybe a colored terminal output if feeling fancy).

7. **Tuning** — Once running end-to-end, the real work is adjusting `config.yaml` palette values until the lights feel right. This is iterative and subjective.

## Key Implementation Notes

- **Always use the Hue Remote API** (cloud), not the local API, since this runs on PythonAnywhere, not on the local network.
- **Graceful degradation**: If any API call fails, log it and skip the cycle. Don't crash.
- **Idempotency**: Running the script twice in a row with the same conditions should produce the same result.
- **Secrets management**: All API keys and tokens in `.env`, never in code or config.yaml. Use `${VAR}` references in config that get resolved at runtime.
- **Logging**: Use Python's `logging` module. Log at INFO level: timestamp, sun elevation, weather conditions, resulting HSB values, lights updated. Helpful for debugging palette tuning.
- **North Vancouver specifics**: At latitude 49.32°, there's significant seasonal variation in day length (8hrs in December to 16hrs in June) and sun elevation (max ~64° in summer, ~17° in winter). The palette engine should handle all of this naturally through the sun elevation curve.

## PythonAnywhere Deployment

Using PythonAnywhere's $10/month "Developer" tier.

**Deployment approach:** The Developer plan's scheduled tasks only support hourly or daily intervals, which is too infrequent. Instead, use the plan's **1 always-on task** slot — a script that runs in a continuous loop, executes the main logic, then sleeps for 15 minutes.

Create an `always_on.py` wrapper at the project root:

```python
import time
import logging
from src.main import run

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 15 * 60  # 15 minutes

if __name__ == "__main__":
    while True:
        try:
            run()
        except Exception as e:
            logger.error(f"Run failed: {e}")
        time.sleep(INTERVAL_SECONDS)
```

`main.py` should expose a `run()` function that handles a single cycle (fetch environment, calculate palette, push to Hue).

**Setup steps:**

1. Sign up for PythonAnywhere Developer plan ($10/month)
2. Upload project files via the Files tab or clone from git in a Bash console
3. In a Bash console: `cd ~/hue-ambient && pip install -r requirements.txt`
4. Create `.env` file: `nano ~/hue-ambient/.env` and paste in API keys
5. Test manually: `cd ~/hue-ambient && python -c "from src.main import run; run()"`
6. Go to the "Tasks" tab → Always-on tasks → set command to: `cd ~/hue-ambient && python always_on.py`
