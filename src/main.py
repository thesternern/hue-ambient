#!/usr/bin/env python3
"""
Main entry point. Fetches environment data, computes palette, pushes to Hue.
Designed to be run every 15 minutes via PythonAnywhere cron.
"""
import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Ensure project root is on path when run directly
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.environment import get_environment, EnvironmentState, get_sun_position
from src.palette import compute_hsb
from src.hue_api import HueClient

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_FILE = PROJECT_ROOT / "config.yaml"
LIGHTS_CONFIG_FILE = PROJECT_ROOT / "lights_config.json"
TOKENS_FILE = Path(os.getenv("TOKENS_PATH", PROJECT_ROOT / "tokens.json"))


def load_config(path: Path) -> dict:
    """Load config.yaml, resolving ${VAR} references from environment."""
    with open(path) as f:
        raw = f.read()

    def replace_var(m):
        return os.getenv(m.group(1), m.group(0))

    raw = re.sub(r'\$\{(\w+)\}', replace_var, raw)
    return yaml.safe_load(raw)


def load_lights_config(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


CONDITION_IDS = {
    "clear": 800, "clouds": 801, "rain": 501,
    "drizzle": 300, "snow": 601, "fog": 741, "mist": 701,
}

def dry_run_state(lat: float, lon: float, clouds: float = 0,
                  condition: str = "clear", temp: float = 15.0) -> EnvironmentState:
    """Build an EnvironmentState using real sun position with manually specified weather."""
    import zoneinfo
    now = datetime.now(zoneinfo.ZoneInfo("America/Vancouver"))
    elev, azim = get_sun_position(now, lat, lon)
    condition_id = CONDITION_IDS.get(condition.lower(), 800)
    return EnvironmentState(
        sun_elevation=elev, sun_azimuth=azim,
        condition=condition.capitalize(), condition_id=condition_id,
        cloud_cover=clouds, temperature_c=temp,
        humidity=60, visibility_m=10000, wind_speed_ms=2.0,
        is_rain=200 <= condition_id < 700,
        is_snow=600 <= condition_id < 700,
        is_fog=700 <= condition_id < 800,
        timestamp=now,
    )


def run(config: dict, lights_config: dict, dry_run: bool = False) -> None:
    lat = config["location"]["latitude"]
    lon = config["location"]["longitude"]
    transition_s = config["schedule"]["transition_seconds"]
    palette_cfg = config.get("palette", {})
    bri_mult = palette_cfg.get("brightness_multiplier", 1.0)
    sat_mult = palette_cfg.get("saturation_multiplier", 1.0)

    # 1. Fetch environment
    if dry_run:
        state = dry_run_state(lat, lon,
                              clouds=config.get("_dry_clouds", 0),
                              condition=config.get("_dry_condition", "clear"),
                              temp=config.get("_dry_temp", 15.0))
        logger.info("DRY RUN: elev=%.1f° condition=%s clouds=%.0f%% temp=%.1f°C",
                    state.sun_elevation, state.condition, state.cloud_cover, state.temperature_c)
    else:
        owm_key = config["api_keys"]["openweathermap"]
        try:
            state = get_environment(owm_key, lat, lon)
        except Exception as e:
            logger.error("Failed to fetch environment data: %s — skipping cycle", e)
            return

    # 2. Compute palette
    # Pass the whole palette section through - hand-listing keys here meant new
    # tunables in config.yaml were silently ignored in favour of code defaults.
    h, s, b = compute_hsb(
        state,
        palette_config=palette_cfg,
        brightness_multiplier=bri_mult,
        saturation_multiplier=sat_mult,
        brightness_floor=palette_cfg.get("brightness_floor", 0),
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
        logger.error("Failed to update Hue lights: %s — retrying once", e)
        try:
            client.set_all_lights(light_ids, h, s, b, transition_seconds=transition_s)
        except Exception as e2:
            logger.error("Retry also failed: %s — skipping cycle", e2)
            return

    logger.info(
        "Cycle complete: elev=%.1f° cond=%s -> H=%.0f S=%.0f B=%.0f -> %d light(s)",
        state.sun_elevation, state.condition, h, s, b, len(light_ids)
    )


def main():
    parser = argparse.ArgumentParser(description="Hue Ambient Light Sync")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip OWM fetch; specify weather manually")
    parser.add_argument("--clouds", type=float, default=0,
                        help="Cloud cover 0-100 (used with --dry-run)")
    parser.add_argument("--condition", default="clear",
                        choices=list(CONDITION_IDS.keys()),
                        help="Weather condition (used with --dry-run)")
    parser.add_argument("--temp", type=float, default=15.0,
                        help="Temperature °C (used with --dry-run)")
    args = parser.parse_args()

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

    config["_dry_clouds"] = args.clouds
    config["_dry_condition"] = args.condition
    config["_dry_temp"] = args.temp
    run(config, lights_config, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
