import pytest
import json
import time
from src.hue_api import save_tokens, load_tokens, build_light_state


class TestTokenStorage:
    def test_save_and_load_roundtrip(self, tmp_path):
        tokens_file = str(tmp_path / "tokens.json")
        save_tokens("acc123", "ref456", tokens_file)
        data = load_tokens(tokens_file)
        assert data["access_token"] == "acc123"
        assert data["refresh_token"] == "ref456"

    def test_load_missing_returns_none(self, tmp_path):
        data = load_tokens(str(tmp_path / "nonexistent.json"))
        assert data is None

    def test_saved_at_timestamp(self, tmp_path):
        tokens_file = str(tmp_path / "tokens.json")
        before = time.time()
        save_tokens("acc", "ref", tokens_file)
        after = time.time()
        data = load_tokens(tokens_file)
        assert before <= data["saved_at"] <= after


class TestBuildLightState:
    def test_returns_required_keys(self):
        state = build_light_state(35, 70, 80, transition_seconds=60)
        assert "hue" in state
        assert "sat" in state
        assert "bri" in state
        assert "transitiontime" in state
        assert state["on"] is True

    def test_transition_time_in_deciseconds(self):
        state = build_light_state(35, 70, 80, transition_seconds=60)
        assert state["transitiontime"] == 600  # 60s * 10

    def test_hue_range(self):
        state = build_light_state(0, 0, 100)
        assert 0 <= state["hue"] <= 65535

    def test_brightness_min_1(self):
        state = build_light_state(0, 0, 0)
        assert state["bri"] >= 1

    def test_full_values(self):
        state = build_light_state(360, 100, 100)
        assert state["sat"] == 254
        assert state["bri"] == 254
