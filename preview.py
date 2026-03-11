#!/usr/bin/env python3
"""
Preview what colors the palette would generate for any datetime/weather combo.
No API calls needed — pure local calculation.

Usage:
  python3 preview.py
  python3 preview.py --time "2025-06-21 12:00" --clouds 80 --condition rain
  python3 preview.py --time "2025-12-21 16:30" --clouds 30 --temp -2
  python3 preview.py --time "2025-03-15 07:00" --condition fog --visibility 500
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path
import zoneinfo

sys.path.insert(0, str(Path(__file__).parent))

from src.environment import EnvironmentState, get_sun_position
from src.palette import compute_hsb
from src.color_utils import hsb_to_rgb

VANCOUVER_TZ = zoneinfo.ZoneInfo("America/Vancouver")

CONDITION_MAP = {
    "clear":       ("Clear", 800),
    "clouds":      ("Clouds", 801),
    "rain":        ("Rain", 501),
    "drizzle":     ("Drizzle", 300),
    "thunderstorm":("Thunderstorm", 200),
    "snow":        ("Snow", 601),
    "fog":         ("Fog", 741),
    "mist":        ("Mist", 701),
    "haze":        ("Haze", 721),
}


def color_block(r: int, g: int, b: int) -> str:
    """Return a terminal color block using ANSI true-color escape codes."""
    return f"\033[48;2;{r};{g};{b}m          \033[0m"


def main():
    parser = argparse.ArgumentParser(
        description="Preview Hue ambient light colors for any conditions"
    )
    parser.add_argument("--time", default=None,
                        help='Datetime in "YYYY-MM-DD HH:MM" (default: now)')
    parser.add_argument("--clouds", type=float, default=0,
                        help="Cloud cover 0-100 (default: 0)")
    parser.add_argument("--condition", default="clear",
                        choices=list(CONDITION_MAP.keys()),
                        help="Weather condition (default: clear)")
    parser.add_argument("--temp", type=float, default=15.0,
                        help="Temperature °C (default: 15)")
    parser.add_argument("--humidity", type=float, default=60.0,
                        help="Humidity 0-100 (default: 60)")
    parser.add_argument("--wind", type=float, default=2.0,
                        help="Wind speed m/s (default: 2.0)")
    parser.add_argument("--visibility", type=float, default=10000.0,
                        help="Visibility in metres (default: 10000)")
    parser.add_argument("--bri-mult", type=float, default=1.0,
                        help="Brightness multiplier (default: 1.0)")
    parser.add_argument("--sat-mult", type=float, default=1.0,
                        help="Saturation multiplier (default: 1.0)")
    parser.add_argument("--bri-floor", type=float, default=0.0,
                        help="Minimum brightness %% (default: 0, match config.yaml brightness_floor)")
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
        sun_elevation=elev,
        sun_azimuth=azim,
        condition=condition_name,
        condition_id=condition_id,
        cloud_cover=args.clouds,
        temperature_c=args.temp,
        humidity=args.humidity,
        visibility_m=args.visibility,
        wind_speed_ms=args.wind,
        is_rain=is_rain,
        is_snow=is_snow,
        is_fog=is_fog,
        timestamp=dt,
    )

    palette_config = {
        "cloud_desaturation_strength": 0.25,
        "rain_hue_shift": 15,
        "temperature_influence": 0.1,
    }

    h, s, b = compute_hsb(
        state, palette_config,
        brightness_multiplier=args.bri_mult,
        saturation_multiplier=args.sat_mult,
        brightness_floor=args.bri_floor,
    )
    r, g, b_val = hsb_to_rgb(h, s, b)

    phase = "Night"
    if elev > 30:
        phase = "Midday"
    elif elev > 10:
        phase = "Morning/Afternoon"
    elif elev > 0:
        phase = "Golden Hour"
    elif elev > -6:
        phase = "Dawn/Dusk"
    elif elev > -18:
        phase = "Twilight"

    print(f"\n{'='*50}")
    print(f"  Preview: {dt.strftime('%Y-%m-%d %H:%M %Z')}")
    print(f"{'='*50}")
    print(f"  Sun      : {elev:+.1f}° elevation  ({phase})")
    print(f"  Azimuth  : {azim:.0f}°")
    print(f"  Weather  : {condition_name}  clouds={args.clouds:.0f}%  temp={args.temp:.1f}°C")
    print(f"  Humidity : {args.humidity:.0f}%  wind={args.wind:.1f}m/s  vis={args.visibility:.0f}m")
    print(f"{'─'*50}")
    print(f"  HSB      : H={h:.0f}°  S={s:.0f}%  B={b:.0f}%")
    print(f"  RGB      : ({r}, {g}, {b_val})")
    print(f"  Color    : {color_block(r, g, b_val)}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
