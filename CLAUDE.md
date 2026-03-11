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

| Sun Elevation | Phase | Hue Range | Saturation | Brightness |
|---|---|---|---|---|
| < -18° | Deep night | 240-260° (deep indigo/navy) | 60-70% | 8-15% |
| -18° to -6° | Twilight | 260-280° (violet/lavender) | 50-65% | 15-25% |
| -6° to 0° | Dawn/dusk | 20-40° (amber/coral) | 70-85% | 25-50% |
| 0° to 10° | Golden hour | 25-45° (warm amber/peach) | 60-75% | 50-70% |
| 10° to 30° | Morning/afternoon | 35-50° (warm white) | 30-45% | 70-85% |
| 30°+ | Midday | 45-55° (neutral/cool white) | 20-35% | 85-100% |

These values are starting points — they should be tunable via a config file.

**Weather modifiers** — each modifier adjusts the base curve output:

- **Cloud cover** (0-100%): Desaturates proportionally (up to -25% sat at full overcast), shifts hue slightly toward cool (blue), reduces brightness slightly
- **Rain**: Shifts hue toward blue-grey (210-230°), drops brightness by 15-25%, adds a "weight" to the atmosphere
- **Snow**: Adds lavender/cool white tint, increases brightness slightly (reflective quality), high saturation reduction
- **Fog**: Compresses the entire color range toward muted warm grey, significant saturation reduction, moderate brightness
- **Temperature**: Subtle global warm/cool shift — colder temps nudge hue slightly cooler, warmer temps nudge warmer. This should be very subtle, not dominant.
- **Wind**: Could optionally influence transition speed or add slight variability

Modifiers should be **multiplicative/additive adjustments** to the base HSB values, not replacements. They stack naturally.

**Interpolation**: Use cosine interpolation (not linear) between anchor points for smoother, more natural transitions.

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
  cloud_desaturation_strength: 0.25  # How much clouds desaturate (0-1)
  rain_hue_shift: 15  # Degrees to shift toward blue during rain
  temperature_influence: 0.1  # How much temp affects color (0 = none, 1 = heavy)
```

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

Using PythonAnywhere's $5/month "Hacker" tier, which supports scheduled tasks at custom intervals.

Once the project works locally:

1. Upload project files to PythonAnywhere
2. Set environment variables in a `.env` file in the project directory
3. Install dependencies: `pip install -r requirements.txt`
4. Add a scheduled task: `python /home/yourusername/hue-ambient/src/main.py`
5. Set schedule to every 15 minutes
