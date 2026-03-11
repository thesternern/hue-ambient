#!/usr/bin/env python3
"""
One-time setup: Philips Hue OAuth flow + light discovery.

Run this once to authorize the app and discover which lights to control.
Saves tokens to tokens.json and light config to lights_config.json.

Usage:
  python3 setup_hue.py
"""
import json
import os
import sys
import time
import webbrowser
from pathlib import Path
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv

load_dotenv()

HUE_API_BASE = "https://api.meethue.com"
TOKENS_FILE = "tokens.json"
LIGHTS_CONFIG_FILE = "lights_config.json"


def get_oauth_url(client_id: str, state: str = "setup") -> str:
    params = urlencode({
        "clientid": client_id,
        "response_type": "code",
        "state": state,
        "appid": "hue_ambient",
        "deviceid": "pythonanywhere",
        "devicename": "HueAmbient",
    })
    return f"{HUE_API_BASE}/v2/oauth2/authorize?{params}"


def exchange_code_for_tokens(client_id: str, client_secret: str, code: str) -> dict:
    resp = requests.post(
        f"{HUE_API_BASE}/v2/oauth2/token",
        data={"grant_type": "authorization_code", "code": code},
        auth=(client_id, client_secret),
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def create_bridge_user(access_token: str) -> str:
    """Create a whitelisted user on the bridge and return the username."""
    resp = requests.post(
        f"{HUE_API_BASE}/bridge",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json={"devicetype": "hue_ambient#pythonanywhere", "generateclientkey": True},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, list) and "success" in data[0]:
        return data[0]["success"]["username"]
    if isinstance(data, list) and data[0].get("error", {}).get("type") == 101:
        raise RuntimeError(
            "Link button not pressed (or pressed too early). "
            "Press the button on your Hue Bridge, then re-run setup_hue.py."
        )
    raise RuntimeError(f"Unexpected response creating bridge user: {data}")


def discover_lights(access_token: str, bridge_username: str) -> dict:
    """Return all lights from the bridge."""
    resp = requests.get(
        f"{HUE_API_BASE}/bridge/{bridge_username}/lights",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def main():
    client_id = os.getenv("HUE_CLIENT_ID")
    client_secret = os.getenv("HUE_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("ERROR: HUE_CLIENT_ID and HUE_CLIENT_SECRET must be set in .env")
        sys.exit(1)

    print("\n=== Philips Hue Setup ===\n")
    print("Step 1: Authorize the app")
    url = get_oauth_url(client_id)
    print(f"\nOpening authorization URL in browser:\n{url}\n")
    webbrowser.open(url)

    print("After authorizing, you'll be redirected to a URL like:")
    print("  https://your-callback-url?code=XXXX&state=setup")
    code = input("\nPaste the 'code' parameter from the redirect URL: ").strip()

    print("\nStep 2: Exchanging code for tokens...")
    token_data = exchange_code_for_tokens(client_id, client_secret, code)
    access_token = token_data["access_token"]
    refresh_token = token_data["refresh_token"]

    print("\nStep 3: Creating bridge user...")
    print("\n*** IMPORTANT: Press the round link button on top of your Hue Bridge NOW ***")
    input("Then press Enter here to continue...")
    bridge_username = create_bridge_user(access_token)
    print(f"Bridge username: {bridge_username}")

    print("\nStep 4: Discovering lights...")
    lights = discover_lights(access_token, bridge_username)

    print("\nFound lights:")
    for lid, info in lights.items():
        print(f"  [{lid}] {info['name']} — type: {info['type']}")

    selected = input("\nEnter light IDs to control (comma-separated, e.g. 1,2,3): ").strip()
    light_ids = [s.strip() for s in selected.split(",") if s.strip()]

    # Save tokens
    tokens_data = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "bridge_username": bridge_username,
        "saved_at": time.time(),
    }
    with open(TOKENS_FILE, "w") as f:
        json.dump(tokens_data, f, indent=2)
    print(f"\nTokens saved to {TOKENS_FILE}")

    # Save lights config
    lights_config = {
        "light_ids": light_ids,
        "bridge_username": bridge_username,
        "lights_info": {lid: {"name": lights[lid]["name"]} for lid in light_ids if lid in lights},
    }
    with open(LIGHTS_CONFIG_FILE, "w") as f:
        json.dump(lights_config, f, indent=2)
    print(f"Light config saved to {LIGHTS_CONFIG_FILE}")

    print("\n=== Setup complete! ===")
    print("You can now run: python3 src/main.py")


if __name__ == "__main__":
    main()
