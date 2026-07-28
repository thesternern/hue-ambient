"""
Palette engine: maps EnvironmentState -> HSB color values.

Base curve: sun elevation angle drives color through anchor points with
cosine interpolation. Weather modifiers shift/scale the result.

The day is a journey across the colour wheel rather than a single warm band:
indigo night -> violet twilight -> coral horizon -> gold morning -> cool
cyan-white at high summer sun -> gold -> coral -> violet again. Because the
curve is driven by sun elevation, winter (max ~17deg at this latitude) never
reaches the cool end, so a January afternoon stays amber while a July midday
goes cool. That seasonal split is the point.
"""
import math
import logging
from src.environment import EnvironmentState

logger = logging.getLogger(__name__)

# Base curve anchor points: (sun_elevation_degrees, hue, saturation, brightness)
# Elevation values must be sorted ascending.
#
# Saturation is deliberately crushed to single digits across the 46-51deg
# crossover: the hue sweep from gold to cyan passes through green, and green
# light in a room looks wrong. At S<10 the transit reads as plain white.
ANCHOR_POINTS = [
    (-25, 250, 70,   8),   # Deep night: indigo
    (-14, 272, 60,  16),   # Twilight: violet
    (-8,  300, 48,  24),   # Pre-dawn/dusk: mauve
    (-4,  350, 68,  33),   # Horizon: deep coral
    (0,    12, 82,  44),   # Sunrise/sunset: coral-amber
    (8,    22, 80,  63),   # Golden hour: rich amber
    (18,   32, 62,  77),   # Mid morning/afternoon: gold
    (32,   44, 40,  87),   # Warm neutral
    (46,   62, 14,  92),   # Cool gold, desaturating hard
    (51,  165,  5,  96),   # Crossover: effectively white
    (64,  195, 22, 100),   # Summer midday: cool cyan-white
]

# Hue targets for weather blends.
WARM_TARGET = 30.0   # amber, used for the afternoon warmth skew


def cosine_interpolate(a: float, b: float, t: float) -> float:
    """Cosine interpolation between a and b at position t (0-1)."""
    t2 = (1 - math.cos(t * math.pi)) / 2
    return a * (1 - t2) + b * t2


def blend_hue(h_from: float, h_to: float, amount: float) -> float:
    """
    Blend h_from toward h_to by amount (0-1), taking the short way around the
    colour wheel. A naive linear blend between opposing hues walks through the
    middle of the wheel (amber -> violet via cyan), which is never what we want.
    """
    diff = ((h_to - h_from + 180.0) % 360.0) - 180.0
    return (h_from + diff * amount) % 360.0


def blend_hue_descending(h_from: float, h_to: float, amount: float) -> float:
    """
    Blend h_from toward h_to walking *down* the wheel (amber -> red -> magenta
    -> violet -> blue), regardless of which way round is shorter.

    Warm hues sit almost exactly opposite blue-grey, so the short path between
    them is a coin flip - and half the time it lands in green. Forcing the
    descending route keeps bad weather in the red/violet family, which matches
    the night end of the base curve.
    """
    distance = (h_from - h_to) % 360.0
    return (h_from - distance * amount) % 360.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


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
            # Hue wraps around 360deg - take the short path
            h0_adj, h1_adj = h0, h1
            if abs(h1 - h0) > 180:
                if h0 > h1:
                    h1_adj = h1 + 360
                else:
                    h0_adj = h0 + 360
            return (
                cosine_interpolate(h0_adj, h1_adj, t) % 360,
                cosine_interpolate(s0, s1, t),
                cosine_interpolate(b0, b1, t),
            )
    return float(ANCHOR_POINTS[-1][1]), float(ANCHOR_POINTS[-1][2]), float(ANCHOR_POINTS[-1][3])


def get_base_hsb(elevation: float) -> tuple[float, float, float]:
    """Return base HSB for a given sun elevation angle."""
    return _interpolate_anchors(elevation)


def apply_solar_asymmetry(
    hsb: tuple[float, float, float],
    state: EnvironmentState,
    config: dict,
) -> tuple[float, float, float]:
    """
    Break the symmetry of the day using sun azimuth.

    Sun elevation alone is symmetric about solar noon, so 9am and 3pm produce
    an identical colour. Azimuth tells us which side of noon we are on, and
    real afternoon light is warmer and hazier than morning light. This makes
    the two halves of the day distinguishable.
    """
    h, s, b = hsb
    strength = config.get("azimuth_warmth", 0.10)
    if strength <= 0:
        return h, s, b

    # Ramp in as the sun clears the horizon - azimuth is meaningless at night.
    daylight = _clamp(state.sun_elevation / 8.0, 0.0, 1.0)
    if daylight <= 0:
        return h, s, b

    # -1 = well before noon, 0 = solar noon, +1 = well after.
    az_offset = ((state.sun_azimuth - 180.0 + 180.0) % 360.0) - 180.0
    afternoon = _clamp(az_offset / 60.0, -1.0, 1.0) * daylight

    h = blend_hue(h, WARM_TARGET, strength * afternoon)
    s *= 1.0 + 0.08 * afternoon
    return h, s, b


def apply_weather_modifiers(
    base_hsb: tuple[float, float, float],
    state: EnvironmentState,
    config: dict,
) -> tuple[float, float, float]:
    """
    Apply weather modifiers to base HSB. All adjustments are additive/multiplicative
    on top of the base - never replacements.
    """
    h, s, b = base_hsb
    cloud_strength = config.get("cloud_desaturation_strength", 0.25)
    temp_influence = config.get("temperature_influence", 0.1)

    h, s, b = apply_solar_asymmetry((h, s, b), state, config)

    # Clear sky: vivid saturation boost when sun is up and clouds are low.
    # Multiplicative on purpose - an additive boost would re-saturate the
    # near-white high-sun crossover straight back into visible green.
    clear_sky_boost = config.get("clear_sky_saturation_boost", 20)
    if state.sun_elevation > 10 and state.cloud_cover < 30:
        clear_factor = 1.0 - (state.cloud_cover / 30.0)  # 1.0 at 0% clouds -> 0.0 at 30%
        s *= 1.0 + (clear_sky_boost / 100.0) * clear_factor
        b += 5 * clear_factor

    # Cloud cover: desaturate + brightness drop. Deliberately no hue push -
    # overcast removes colour, it does not add one, and nudging a warm hue
    # upward only walks it toward yellow-green.
    cloud_factor = state.cloud_cover / 100.0
    s -= cloud_factor * cloud_strength * 100  # up to -25 sat at full overcast
    b -= cloud_factor * 8                     # slight brightness drop

    # Thunderstorm: dramatic violet pull, lower brightness. Short-path blend so
    # it travels amber -> red -> magenta -> violet instead of through cyan.
    thunderstorm_hue_target = config.get("thunderstorm_hue_target", 265)
    if 200 <= state.condition_id <= 299:
        storm_intensity = min(state.cloud_cover / 100.0, 1.0)
        b -= 30 * storm_intensity
        s = min(100.0, s + 15 * storm_intensity)
        h = blend_hue_descending(h, thunderstorm_hue_target, 0.7 * storm_intensity)

    # Rain: blue-grey and heavier. The hue blend is scaled by how desaturated
    # the colour already is, so vivid colours grey out before they swing round
    # the wheel - that keeps the transit invisible instead of magenta.
    elif state.is_rain and not state.is_snow:
        rain_hue_target = config.get("rain_hue_target", 215)
        rain_intensity = min(state.cloud_cover / 100.0, 1.0)
        b -= 20 * rain_intensity
        s -= 10 * rain_intensity
        greyness = 1.0 - _clamp(s / 100.0, 0.0, 1.0)
        h = blend_hue_descending(h, rain_hue_target, rain_intensity * greyness)

    # Snow: cool lavender tint, slight brightness boost (reflective), desaturate
    if state.is_snow:
        s -= 20
        b += 5   # reflective boost
        h = blend_hue(h, 280, 0.25)  # lavender

    # Fog: muted warm grey, significant desaturation
    if state.is_fog:
        fog_factor = max(0.0, 1 - (state.visibility_m / 10000))
        s -= fog_factor * 30
        b -= fog_factor * 10
        h = blend_hue(h, 35, fog_factor * 0.3)  # nudge toward warm grey

    # Wind: a blustery day feels more alive than a still one. Very subtle.
    wind_influence = config.get("wind_influence", 0.15)
    if wind_influence > 0:
        wind_factor = _clamp(state.wind_speed_ms / 12.0, 0.0, 1.0)
        s *= 1.0 + wind_factor * wind_influence * 0.4
        b += wind_factor * wind_influence * 10

    # Temperature: very subtle warm/cool nudge
    # 15degC = neutral; colder nudges cool (+hue), warmer nudges warm (-hue)
    temp_delta = (15.0 - state.temperature_c) * temp_influence
    h += temp_delta * 0.5  # very subtle - max +/-5deg hue at 10degC deviation

    # Clamp all values
    h = h % 360
    s = _clamp(s, 0.0, 100.0)
    b = _clamp(b, 0.0, 100.0)

    return h, s, b


def apply_brightness_floor(b: float, floor: float) -> float:
    """
    Compress the 0-100 brightness range into floor-100 instead of clamping at
    the floor.

    A hard clamp flattened every value below the floor to exactly the floor,
    which erased the whole night arc - deep night, twilight and dawn all came
    out identical. Compressing keeps the lights usably bright while preserving
    the relative shape of the curve.
    """
    if floor <= 0:
        return b
    floor = _clamp(floor, 0.0, 100.0)
    return floor + (_clamp(b, 0.0, 100.0) / 100.0) * (100.0 - floor)


def compute_hsb(
    state: EnvironmentState,
    palette_config: dict | None = None,
    brightness_multiplier: float = 1.0,
    saturation_multiplier: float = 1.0,
    brightness_floor: float = 0.0,
) -> tuple[float, float, float]:
    """
    Full pipeline: EnvironmentState -> HSB ready for the Hue API.
    palette_config keys: cloud_desaturation_strength, temperature_influence,
                         clear_sky_saturation_boost, thunderstorm_hue_target,
                         rain_hue_target, azimuth_warmth, wind_influence
    brightness_floor: brightness is compressed into floor-100 (not clamped),
                      so night keeps its shape while staying ambient.
    """
    if palette_config is None:
        palette_config = {}

    base = get_base_hsb(state.sun_elevation)
    h, s, b = apply_weather_modifiers(base, state, palette_config)

    # Apply global multipliers, then compress into the floor..100 range
    s = _clamp(s * saturation_multiplier, 0.0, 100.0)
    b = _clamp(b * brightness_multiplier, 0.0, 100.0)
    b = apply_brightness_floor(b, brightness_floor)
    b = max(1.0, b)  # Hue API requires bri >= 1

    logger.info(
        "Palette: elev=%.1f° az=%.0f° -> base H=%.0f S=%.0f B=%.0f -> final H=%.0f S=%.0f B=%.0f",
        state.sun_elevation, state.sun_azimuth,
        base[0], base[1], base[2], h, s, b
    )
    return round(h, 1), round(s, 1), round(b, 1)
