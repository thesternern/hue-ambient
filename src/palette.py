"""
Palette engine: maps EnvironmentState -> HSB color values.

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
    (-12, 270, 60, 20),   # Twilight: violet/lavender
    (-3,  28,  85, 38),   # Dawn/dusk: rose-coral, vivid
    (5,   32,  80, 62),   # Golden hour: rich warm amber
    (20,  40,  58, 78),   # Morning/afternoon: warm gold
    (45,  48,  45, 92),   # Midday: golden-warm, not white
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

    # Clear sky: vivid saturation boost when sun is up and clouds are low
    clear_sky_boost = config.get("clear_sky_saturation_boost", 20)
    if state.sun_elevation > 10 and state.cloud_cover < 30:
        clear_factor = 1.0 - (state.cloud_cover / 30.0)  # 1.0 at 0% clouds → 0.0 at 30%
        s += clear_sky_boost * clear_factor
        b += 5 * clear_factor

    # Cloud cover: desaturate + slight brightness drop + cool hue shift
    cloud_factor = state.cloud_cover / 100.0
    s -= cloud_factor * cloud_strength * 100  # up to -25 sat at full overcast
    b -= cloud_factor * 8                     # slight brightness drop
    h += cloud_factor * 5                     # slight cool shift

    # Thunderstorm: dramatic violet pull, lower brightness
    thunderstorm_hue_target = config.get("thunderstorm_hue_target", 265)
    if 200 <= state.condition_id <= 299:
        storm_intensity = min(state.cloud_cover / 100.0, 1.0)
        h = h * (1 - 0.7 * storm_intensity) + thunderstorm_hue_target * (0.7 * storm_intensity)
        b -= 30 * storm_intensity
        s = min(100.0, s + 15 * storm_intensity)
    # Rain: shift toward blue-grey, drop brightness
    elif state.is_rain and not state.is_snow:
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
    brightness_floor: float = 0.0,
) -> tuple[float, float, float]:
    """
    Full pipeline: EnvironmentState -> HSB ready for the Hue API.
    palette_config keys: cloud_desaturation_strength, rain_hue_shift, temperature_influence,
                         clear_sky_saturation_boost, thunderstorm_hue_target
    brightness_floor: minimum brightness % (e.g. 60 keeps lights ambient at night)
    """
    if palette_config is None:
        palette_config = {
            "cloud_desaturation_strength": 0.25,
            "rain_hue_shift": 15,
            "temperature_influence": 0.1,
        }

    base = get_base_hsb(state.sun_elevation)
    h, s, b = apply_weather_modifiers(base, state, palette_config)

    # Apply global multipliers, then floor
    s = max(0.0, min(100.0, s * saturation_multiplier))
    b = max(brightness_floor, min(100.0, b * brightness_multiplier))
    b = max(1.0, b)  # Hue API requires bri >= 1

    logger.info(
        "Palette: elev=%.1f° -> base H=%.0f S=%.0f B=%.0f -> final H=%.0f S=%.0f B=%.0f",
        state.sun_elevation, base[0], base[1], base[2], h, s, b
    )
    return round(h, 1), round(s, 1), round(b, 1)
