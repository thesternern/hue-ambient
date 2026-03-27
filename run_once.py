#!/usr/bin/env python3
"""
Single-run entry point for cron-based deployments (e.g. Railway cron service).

Unlike always_on.py which loops forever, this runs one cycle and exits.
"""
import json
import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from src.main import load_config, load_lights_config, run
from src.hue_api import HueClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("run_once")

PROJECT_ROOT = Path(__file__).parent
CONFIG_FILE = PROJECT_ROOT / "config.yaml"
LIGHTS_CONFIG_FILE = PROJECT_ROOT / "lights_config.json"
TOKENS_FILE = Path(os.getenv("TOKENS_PATH", PROJECT_ROOT / "tokens.json"))


def bootstrap_files():
    """Create or sync tokens.json and lights_config.json from env vars.

    Uses env_refresh_token to track the env var we bootstrapped from.
    Only overwrites tokens.json when the user changes the env var,
    NOT when Hue rotates the refresh token during normal operation.
    """
    refresh_token = os.getenv("HUE_REFRESH_TOKEN")
    bridge_username = os.getenv("HUE_BRIDGE_USERNAME")

    if refresh_token and bridge_username:
        if TOKENS_FILE.exists():
            with open(TOKENS_FILE) as f:
                existing = json.load(f)
            # Only overwrite if the env var itself changed (user updated it).
            # Compare against env_refresh_token (the original seed), not
            # refresh_token (which Hue may have rotated).
            if existing.get("env_refresh_token") != refresh_token:
                data = {
                    "access_token": "",
                    "refresh_token": refresh_token,
                    "env_refresh_token": refresh_token,
                    "bridge_username": bridge_username,
                    "saved_at": time.time(),
                }
                with open(TOKENS_FILE, "w") as f:
                    json.dump(data, f, indent=2)
                logger.info("Synced tokens.json with updated environment variable")
        else:
            data = {
                "access_token": "",
                "refresh_token": refresh_token,
                "env_refresh_token": refresh_token,
                "bridge_username": bridge_username,
                "saved_at": time.time(),
            }
            with open(TOKENS_FILE, "w") as f:
                json.dump(data, f, indent=2)
            logger.info("Bootstrapped tokens.json from environment variables")
    elif not TOKENS_FILE.exists():
        logger.warning("tokens.json missing and HUE_REFRESH_TOKEN/HUE_BRIDGE_USERNAME not set")

    if not LIGHTS_CONFIG_FILE.exists():
        light_ids = os.getenv("HUE_LIGHT_IDS")
        bridge_username = os.getenv("HUE_BRIDGE_USERNAME")
        if light_ids and bridge_username:
            data = {
                "light_ids": [s.strip() for s in light_ids.split(",") if s.strip()],
                "bridge_username": bridge_username,
                "lights_info": {},
            }
            with open(LIGHTS_CONFIG_FILE, "w") as f:
                json.dump(data, f, indent=2)
            logger.info("Bootstrapped lights_config.json from environment variables")
        else:
            logger.warning("lights_config.json missing and HUE_LIGHT_IDS/HUE_BRIDGE_USERNAME not set")


def force_color_override(config, lights_config):
    """Push a specific HSB color directly, bypassing the palette engine.
    Set FORCE_COLOR env var to 'H,S,B' (e.g. '280,80,80' for purple)."""
    parts = os.getenv("FORCE_COLOR", "").split(",")
    if len(parts) != 3:
        return False
    h, s, b = float(parts[0]), float(parts[1]), float(parts[2])
    logger.info("FORCE_COLOR override: H=%.0f S=%.0f B=%.0f", h, s, b)
    hue_cfg = config["hue"]
    client = HueClient(
        client_id=hue_cfg["client_id"],
        client_secret=hue_cfg["client_secret"],
        tokens_file=str(TOKENS_FILE),
    )
    light_ids = lights_config["light_ids"]
    client.set_all_lights(light_ids, h, s, b, transition_seconds=5)
    logger.info("Force color pushed to %d light(s)", len(light_ids))
    return True


if __name__ == "__main__":
    bootstrap_files()
    config = load_config(CONFIG_FILE)
    lights_config = load_lights_config(LIGHTS_CONFIG_FILE)
    try:
        if not force_color_override(config, lights_config):
            run(config, lights_config)
    except Exception as e:
        logger.error("Run failed: %s", e)
        sys.exit(1)
