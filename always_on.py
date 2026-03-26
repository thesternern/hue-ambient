#!/usr/bin/env python3
"""
Always-on task wrapper.
Runs the main pipeline every 15 minutes in an infinite loop.

Works on both PythonAnywhere and Railway. On Railway, tokens.json and
lights_config.json are bootstrapped from environment variables on first run.
"""
import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

import json
from src.main import load_config, load_lights_config, run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("always_on")

INTERVAL_SECONDS = 15 * 60  # 15 minutes
PROJECT_ROOT = Path(__file__).parent
CONFIG_FILE = PROJECT_ROOT / "config.yaml"
LIGHTS_CONFIG_FILE = PROJECT_ROOT / "lights_config.json"
TOKENS_FILE = PROJECT_ROOT / "tokens.json"


def bootstrap_files():
    """Create tokens.json and lights_config.json from env vars if they don't exist.

    This allows Railway (or any fresh deploy) to start without manually
    copying these gitignored files. Existing files are never overwritten.
    """
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
    logger.info("Always-on task started. Running every %d minutes.", INTERVAL_SECONDS // 60)
    bootstrap_files()
    config = load_config(CONFIG_FILE)
    lights_config = load_lights_config(LIGHTS_CONFIG_FILE)

    while True:
        try:
            run(config, lights_config)
        except Exception as e:
            logger.error("Run failed: %s — will retry next cycle", e)
        logger.info("Sleeping %d minutes until next cycle...", INTERVAL_SECONDS // 60)
        time.sleep(INTERVAL_SECONDS)
