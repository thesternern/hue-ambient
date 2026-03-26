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
    """Create tokens.json and lights_config.json from env vars if they don't exist."""
    if not TOKENS_FILE.exists():
        refresh_token = os.getenv("HUE_REFRESH_TOKEN")
        bridge_username = os.getenv("HUE_BRIDGE_USERNAME")
        if refresh_token and bridge_username:
            data = {
                "access_token": "",
                "refresh_token": refresh_token,
                "bridge_username": bridge_username,
                "saved_at": time.time(),
            }
            with open(TOKENS_FILE, "w") as f:
                json.dump(data, f, indent=2)
            logger.info("Bootstrapped tokens.json from environment variables")
        else:
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


if __name__ == "__main__":
    bootstrap_files()
    config = load_config(CONFIG_FILE)
    lights_config = load_lights_config(LIGHTS_CONFIG_FILE)
    try:
        run(config, lights_config)
    except Exception as e:
        logger.error("Run failed: %s", e)
        sys.exit(1)
