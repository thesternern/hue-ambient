"""
Philips Hue Remote API client.

Token flow:
  1. Initial tokens obtained via setup_hue.py OAuth flow
  2. Access token stored in tokens.json (expires periodically)
  3. Refresh token used to get new access token when expired
  4. Updated tokens saved back to tokens.json
"""
import json
import logging
import time
from typing import Optional

import requests

from src.color_utils import hsb_to_hue_api

logger = logging.getLogger(__name__)

TOKENS_FILE = "tokens.json"
HUE_API_BASE = "https://api.meethue.com"


def save_tokens(access_token: str, refresh_token: str, path: str = TOKENS_FILE) -> None:
    """Persist tokens to JSON file."""
    with open(path, "w") as f:
        json.dump({
            "access_token": access_token,
            "refresh_token": refresh_token,
            "saved_at": time.time(),
        }, f, indent=2)


def load_tokens(path: str = TOKENS_FILE) -> Optional[dict]:
    """Load tokens from JSON file. Returns None if file doesn't exist."""
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> dict:
    """Use refresh token to get a new access token. Returns new token dict."""
    resp = requests.post(
        f"{HUE_API_BASE}/v2/oauth2/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        auth=(client_id, client_secret),
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    return {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token", refresh_token),
    }


def build_light_state(
    hue_deg: float, sat_pct: float, bri_pct: float, transition_seconds: int = 60
) -> dict:
    """Build the Hue API light state dict from HSB values."""
    hue_val, sat_val, bri_val = hsb_to_hue_api(hue_deg, sat_pct, bri_pct)
    return {
        "on": True,
        "hue": hue_val,
        "sat": sat_val,
        "bri": bri_val,
        "transitiontime": transition_seconds * 10,  # deciseconds
    }


class HueClient:
    """Client for the Philips Hue Remote API."""

    def __init__(self, client_id: str, client_secret: str, tokens_file: str = TOKENS_FILE):
        self.client_id = client_id
        self.client_secret = client_secret
        self.tokens_file = tokens_file
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._bridge_username: Optional[str] = None
        self._load_tokens()

    def _load_tokens(self) -> None:
        data = load_tokens(self.tokens_file)
        if data:
            self._access_token = data["access_token"]
            self._refresh_token = data["refresh_token"]
            self._bridge_username = data.get("bridge_username")

    def _ensure_token(self) -> None:
        """Refresh access token."""
        if not self._refresh_token:
            raise RuntimeError("No refresh token. Run setup_hue.py first.")
        new_tokens = refresh_access_token(
            self.client_id, self.client_secret, self._refresh_token
        )
        self._access_token = new_tokens["access_token"]
        self._refresh_token = new_tokens["refresh_token"]
        # Preserve bridge_username when updating tokens
        tokens_data = load_tokens(self.tokens_file) or {}
        with open(self.tokens_file, "w") as f:
            json.dump({
                **tokens_data,
                "access_token": self._access_token,
                "refresh_token": self._refresh_token,
                "saved_at": time.time(),
            }, f, indent=2)
        logger.info("Access token refreshed successfully")

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

    def _api_url(self, path: str) -> str:
        return f"{HUE_API_BASE}/bridge/{self._bridge_username}/{path}"

    def _request(self, method: str, path: str, **kwargs) -> dict:
        """Make an API request, refreshing token on 401."""
        url = self._api_url(path)
        resp = requests.request(method, url, headers=self._headers(), timeout=10, **kwargs)
        if resp.status_code == 401:
            logger.info("Token expired, refreshing...")
            self._ensure_token()
            resp = requests.request(method, url, headers=self._headers(), timeout=10, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def get_lights(self) -> dict:
        """Return all lights from the bridge."""
        return self._request("GET", "lights")

    def set_light_state(self, light_id: str, state: dict) -> None:
        """Push a state dict to a single light."""
        self._request("PUT", f"lights/{light_id}/state", json=state)
        logger.debug("Light %s updated: %s", light_id, state)

    def set_all_lights(
        self,
        light_ids: list[str],
        hue_deg: float,
        sat_pct: float,
        bri_pct: float,
        transition_seconds: int = 60,
    ) -> None:
        """Push HSB values to all configured lights."""
        state = build_light_state(hue_deg, sat_pct, bri_pct, transition_seconds)
        errors = []
        for light_id in light_ids:
            try:
                self.set_light_state(light_id, state)
            except Exception as e:
                logger.error("Failed to update light %s: %s", light_id, e)
                errors.append(light_id)
        if errors:
            logger.warning("Failed to update lights: %s", errors)
        else:
            logger.info(
                "Updated %d light(s): H=%.0f° S=%.0f%% B=%.0f%%",
                len(light_ids), hue_deg, sat_pct, bri_pct
            )
