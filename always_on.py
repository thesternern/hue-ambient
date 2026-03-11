#!/usr/bin/env python3
"""
PythonAnywhere always-on task wrapper.
Runs the main pipeline every 15 minutes in an infinite loop.

Start this as an always-on task in PythonAnywhere:
  cd ~/hue-ambient && python always_on.py
"""
import logging
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

if __name__ == "__main__":
    logger.info("Always-on task started. Running every %d minutes.", INTERVAL_SECONDS // 60)
    config = load_config(CONFIG_FILE)
    lights_config = load_lights_config(LIGHTS_CONFIG_FILE)

    while True:
        try:
            run(config, lights_config)
        except Exception as e:
            logger.error("Run failed: %s — will retry next cycle", e)
        logger.info("Sleeping %d minutes until next cycle...", INTERVAL_SECONDS // 60)
        time.sleep(INTERVAL_SECONDS)
