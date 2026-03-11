#!/usr/bin/env python3
"""
Quick test: push a specific color to lights to verify Hue connectivity.
Usage:
  python3 test_lights.py green
  python3 test_lights.py blue
  python3 test_lights.py red
  python3 test_lights.py warm    # warm amber
  python3 test_lights.py off
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
import os
from src.hue_api import HueClient, build_light_state

load_dotenv()

COLORS = {
    "red":   (0,   100, 80),
    "green": (120, 100, 80),
    "blue":  (240, 100, 80),
    "warm":  (35,  90,  80),
    "white": (0,   0,   100),
    "off":   None,
}

color_name = sys.argv[1].lower() if len(sys.argv) > 1 else "green"
if color_name not in COLORS:
    print(f"Unknown color '{color_name}'. Choose from: {', '.join(COLORS)}")
    sys.exit(1)

with open("lights_config.json") as f:
    lights_config = json.load(f)

client = HueClient(
    client_id=os.getenv("HUE_CLIENT_ID"),
    client_secret=os.getenv("HUE_CLIENT_SECRET"),
    tokens_file="tokens.json",
)

light_ids = lights_config["light_ids"]

if color_name == "off":
    for lid in light_ids:
        client.set_light_state(lid, {"on": False, "transitiontime": 10})
    print(f"Turned off lights: {light_ids}")
else:
    h, s, b = COLORS[color_name]
    state = build_light_state(h, s, b, transition_seconds=1)
    for lid in light_ids:
        client.set_light_state(lid, state)
    print(f"Set lights {light_ids} to {color_name.upper()} (H={h} S={s} B={b})")
