#!/usr/bin/env python3
"""
Generate an HTML visualization of the palette engine output across a full day.

Usage:
  python3 visualize_palette.py                         # today's date
  python3 visualize_palette.py --date "2026-06-21"     # specific date
  python3 visualize_palette.py --season-compare        # summer/winter/equinox side-by-side
"""
import argparse
import sys
from datetime import datetime, timedelta, date
from pathlib import Path
import zoneinfo

import yaml
from astral import LocationInfo
from astral.sun import sun as astral_sun

sys.path.insert(0, str(Path(__file__).parent))

from src.environment import EnvironmentState, get_sun_position
from src.palette import compute_hsb, ANCHOR_POINTS
from src.color_utils import hsb_to_rgb

VANCOUVER_TZ = zoneinfo.ZoneInfo("America/Vancouver")
LAT, LON = 49.3200, -123.0724

WEATHER_SCENARIOS = {
    "Clear":  {"condition": "Clear",  "condition_id": 800, "cloud_cover": 0,  "is_rain": False, "is_snow": False, "is_fog": False, "visibility_m": 10000, "temp": 15},
    "Cloudy": {"condition": "Clouds", "condition_id": 801, "cloud_cover": 85, "is_rain": False, "is_snow": False, "is_fog": False, "visibility_m": 10000, "temp": 12},
    "Rain":   {"condition": "Rain",   "condition_id": 501, "cloud_cover": 90, "is_rain": True,  "is_snow": False, "is_fog": False, "visibility_m": 5000,  "temp": 10},
    "Snow":   {"condition": "Snow",   "condition_id": 601, "cloud_cover": 80, "is_rain": True,  "is_snow": True,  "is_fog": False, "visibility_m": 3000,  "temp": -2},
    "Fog":    {"condition": "Fog",    "condition_id": 741, "cloud_cover": 60, "is_rain": False, "is_snow": False, "is_fog": True,  "visibility_m": 800,   "temp": 8},
}

ANCHOR_LABELS = [
    "Deep Night", "Twilight", "Pre-dawn",
    "Dawn/Dusk", "Golden Hour", "Morning/Afternoon", "Midday",
]


def load_palette_config():
    """Load palette config from config.yaml."""
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)
    return config.get("palette", {})


def make_env_state(dt, scenario):
    """Build EnvironmentState from a datetime and weather scenario dict."""
    elev, azim = get_sun_position(dt, LAT, LON)
    return EnvironmentState(
        sun_elevation=elev,
        sun_azimuth=azim,
        condition=scenario["condition"],
        condition_id=scenario["condition_id"],
        cloud_cover=scenario["cloud_cover"],
        temperature_c=scenario["temp"],
        humidity=60,
        visibility_m=scenario["visibility_m"],
        wind_speed_ms=2.0,
        is_rain=scenario["is_rain"],
        is_snow=scenario["is_snow"],
        is_fog=scenario["is_fog"],
        timestamp=dt,
    )


def compute_color(dt, scenario, palette_cfg):
    """Compute palette output for a datetime + scenario. Returns dict with all values."""
    state = make_env_state(dt, scenario)
    cfg = {
        "cloud_desaturation_strength": palette_cfg.get("cloud_desaturation_strength", 0.25),
        "rain_hue_shift": palette_cfg.get("rain_hue_shift", 15),
        "temperature_influence": palette_cfg.get("temperature_influence", 0.1),
        "clear_sky_saturation_boost": palette_cfg.get("clear_sky_saturation_boost", 20),
        "thunderstorm_hue_target": palette_cfg.get("thunderstorm_hue_target", 265),
    }
    bri_mult = palette_cfg.get("brightness_multiplier", 1.0)
    sat_mult = palette_cfg.get("saturation_multiplier", 1.0)
    bri_floor = palette_cfg.get("brightness_floor", 0)

    h, s, b = compute_hsb(state, cfg, bri_mult, sat_mult, bri_floor)
    r, g, b_rgb = hsb_to_rgb(h, s, b)
    return {
        "time": dt.strftime("%H:%M"),
        "elev": state.sun_elevation,
        "h": h, "s": s, "b": b,
        "r": r, "g": g, "b_rgb": b_rgb,
    }


def compute_timeline(target_date, palette_cfg):
    """Compute 96 samples (every 15 min) for each weather scenario."""
    results = {}
    for name, scenario in WEATHER_SCENARIOS.items():
        samples = []
        for i in range(96):
            minutes = i * 15
            dt = datetime(target_date.year, target_date.month, target_date.day,
                          minutes // 60, minutes % 60, tzinfo=VANCOUVER_TZ)
            samples.append(compute_color(dt, scenario, palette_cfg))
        results[name] = samples
    return results


def get_sun_events(target_date):
    """Get key sun events for the date. Returns dict of name -> datetime."""
    loc = LocationInfo(latitude=LAT, longitude=LON)
    events = {}
    try:
        s = astral_sun(loc.observer, date=target_date, tzinfo=VANCOUVER_TZ)
        for key in ("dawn", "sunrise", "noon", "sunset", "dusk"):
            if key in s:
                events[key] = s[key]
    except Exception:
        pass
    return events


def compute_key_moments(target_date, palette_cfg):
    """Compute colors at key sun events + midnight for each scenario."""
    sun_events = get_sun_events(target_date)

    moments = [("Midnight", datetime(target_date.year, target_date.month, target_date.day,
                                     0, 0, tzinfo=VANCOUVER_TZ))]
    for name in ("dawn", "sunrise", "noon", "sunset", "dusk"):
        if name in sun_events:
            moments.append((name.capitalize(), sun_events[name]))

    results = []
    for moment_name, dt in moments:
        row = {"moment": moment_name, "time": dt.strftime("%H:%M"), "colors": {}}
        for scenario_name, scenario in WEATHER_SCENARIOS.items():
            row["colors"][scenario_name] = compute_color(dt, scenario, palette_cfg)
        results.append(row)
    return results


# --------------- HTML rendering ---------------

CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: #1a1a2e; color: #e0e0e0; font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; padding: 40px; max-width: 1200px; margin: 0 auto; }
h1 { font-size: 1.6em; margin-bottom: 4px; color: #fff; }
h2 { font-size: 1.2em; margin: 40px 0 16px; color: #ccc; border-bottom: 1px solid #333; padding-bottom: 6px; }
h3 { font-size: 1em; margin: 24px 0 10px; color: #aaa; }
.subtitle { color: #888; font-size: 0.85em; margin-bottom: 30px; }
.note { color: #666; font-size: 0.75em; font-style: italic; margin-top: 6px; }

/* Timeline bars */
.timeline-group { margin-bottom: 30px; }
.timeline-row { display: flex; align-items: center; margin-bottom: 2px; }
.timeline-label { width: 80px; font-size: 0.8em; color: #999; text-align: right; padding-right: 12px; flex-shrink: 0; }
.timeline-bar { display: flex; flex: 1; height: 36px; border-radius: 3px; overflow: hidden; position: relative; }
.timeline-bar div { flex: 1; transition: opacity 0.1s; }
.timeline-bar div:hover { opacity: 0.7; cursor: crosshair; }
.timeline-axis { display: flex; margin-left: 92px; margin-top: 4px; margin-bottom: 0; }
.timeline-axis span { flex: 1; font-size: 0.7em; color: #666; }
.timeline-markers { position: absolute; top: 0; left: 0; right: 0; bottom: 0; pointer-events: none; }
.timeline-marker { position: absolute; top: 0; height: 100%; width: 1px; background: rgba(255,255,255,0.4); }
.timeline-marker-label { position: absolute; top: -16px; font-size: 0.6em; color: #888; white-space: nowrap; transform: translateX(-50%); }

/* Swatch grid */
.swatch-grid { display: grid; gap: 3px; margin-top: 8px; }
.swatch-header { font-size: 0.75em; color: #999; text-align: center; padding: 4px; }
.swatch-moment { font-size: 0.75em; color: #999; display: flex; align-items: center; justify-content: flex-end; padding-right: 10px; }
.swatch { border-radius: 4px; padding: 8px 6px; text-align: center; min-height: 60px; display: flex; flex-direction: column; justify-content: center; }
.swatch-time { font-size: 0.7em; color: rgba(0,0,0,0.6); font-weight: 600; }
.swatch-detail { font-size: 0.6em; color: rgba(0,0,0,0.5); font-family: monospace; }
.swatch-detail-light { font-size: 0.6em; color: rgba(255,255,255,0.7); font-family: monospace; }
.swatch-time-light { font-size: 0.7em; color: rgba(255,255,255,0.8); font-weight: 600; }

/* Anchor points */
.anchors { display: flex; gap: 8px; flex-wrap: wrap; }
.anchor { border-radius: 6px; padding: 14px 12px; text-align: center; flex: 1; min-width: 140px; }
.anchor-name { font-size: 0.8em; font-weight: 600; margin-bottom: 4px; }
.anchor-detail { font-size: 0.7em; font-family: monospace; }

/* Config table */
.config-table { border-collapse: collapse; width: 100%; max-width: 700px; }
.config-table th, .config-table td { padding: 6px 12px; text-align: left; border-bottom: 1px solid #2a2a3e; font-size: 0.85em; }
.config-table th { color: #888; font-weight: normal; }
.config-table td:first-child { font-family: monospace; color: #c9a0dc; }
.config-table td:nth-child(2) { font-family: monospace; color: #fff; }
.config-table td:nth-child(3) { color: #666; font-size: 0.8em; }
"""


def _text_color(r, g, b_rgb):
    """Return 'light' or 'dark' class suffix based on perceived brightness."""
    luma = 0.299 * r + 0.587 * g + 0.114 * b_rgb
    return "light" if luma < 128 else ""


def render_timeline_section(timeline_data, sun_events, date_label):
    """Render one group of timeline bars (one date)."""
    html = f'<h3>{date_label}</h3>\n<div class="timeline-group">\n'

    # Compute marker positions (% of day)
    markers_html = ""
    for event_name, event_dt in sun_events.items():
        pct = (event_dt.hour * 60 + event_dt.minute) / 1440 * 100
        markers_html += (
            f'<div class="timeline-marker" style="left:{pct:.1f}%">'
            f'<span class="timeline-marker-label">{event_name}</span></div>\n'
        )

    for scenario_name, samples in timeline_data.items():
        html += f'<div class="timeline-row">'
        html += f'<div class="timeline-label">{scenario_name}</div>'
        html += f'<div class="timeline-bar">'
        html += f'<div class="timeline-markers">{markers_html}</div>'
        for s in samples:
            title = f"{s['time']} | elev {s['elev']:+.1f}\u00b0 | H={s['h']:.0f} S={s['s']:.0f} B={s['b']:.0f}"
            html += f'<div style="background:rgb({s["r"]},{s["g"]},{s["b_rgb"]})" title="{title}"></div>'
        html += '</div></div>\n'

    # Hour axis
    html += '<div class="timeline-axis">'
    for hour in range(0, 24, 3):
        html += f'<span>{hour:02d}</span>'
    html += '</div>\n'
    html += '</div>\n'
    return html


def render_moments_section(moments_data):
    """Render the key moments swatch grid."""
    scenario_names = list(WEATHER_SCENARIOS.keys())
    cols = len(scenario_names) + 1
    html = f'<div class="swatch-grid" style="grid-template-columns: 100px repeat({len(scenario_names)}, 1fr);">\n'

    # Header row
    html += '<div></div>'
    for name in scenario_names:
        html += f'<div class="swatch-header">{name}</div>'

    for row in moments_data:
        html += f'<div class="swatch-moment">{row["moment"]}<br><span style="font-size:0.85em">{row["time"]}</span></div>'
        for scenario_name in scenario_names:
            c = row["colors"][scenario_name]
            suffix = _text_color(c["r"], c["g"], c["b_rgb"])
            tc = "swatch-time-light" if suffix == "light" else "swatch-time"
            dc = "swatch-detail-light" if suffix == "light" else "swatch-detail"
            html += (
                f'<div class="swatch" style="background:rgb({c["r"]},{c["g"]},{c["b_rgb"]})">'
                f'<div class="{tc}">{c["time"]}</div>'
                f'<div class="{dc}">elev {c["elev"]:+.1f}\u00b0</div>'
                f'<div class="{dc}">H={c["h"]:.0f} S={c["s"]:.0f} B={c["b"]:.0f}</div>'
                f'</div>\n'
            )
    html += '</div>\n'
    return html


def render_anchors_section():
    """Render the 6 anchor point reference swatches."""
    html = '<div class="anchors">\n'
    for i, (elev, h, s, b) in enumerate(ANCHOR_POINTS):
        r, g, b_rgb = hsb_to_rgb(h, s, b)
        suffix = _text_color(r, g, b_rgb)
        name_cls = "anchor-name" + (" swatch-time-light" if suffix == "light" else "")
        detail_cls = "anchor-detail" + (" swatch-detail-light" if suffix == "light" else "")
        html += (
            f'<div class="anchor" style="background:rgb({r},{g},{b_rgb})">'
            f'<div class="{name_cls}">{ANCHOR_LABELS[i]}</div>'
            f'<div class="{detail_cls}">elev {elev:+d}\u00b0</div>'
            f'<div class="{detail_cls}">H={h} S={s} B={b}</div>'
            f'</div>\n'
        )
    html += '</div>\n'
    html += '<p class="note">Raw base curve values — no weather modifiers or config multipliers applied.</p>\n'
    return html


CONFIG_DESCRIPTIONS = {
    "brightness_multiplier": "Global brightness scale",
    "saturation_multiplier": "Global saturation scale",
    "brightness_floor": "Minimum brightness %",
    "cloud_desaturation_strength": "Cloud desaturation factor (0-1)",
    "rain_hue_shift": "Hue shift toward blue in rain (degrees)",
    "temperature_influence": "Temperature hue influence (0-1)",
    "clear_sky_saturation_boost": "Saturation boost on clear days",
    "thunderstorm_hue_target": "Hue target during storms (degrees)",
}


def render_config_section(palette_cfg):
    """Render the current config values table."""
    html = '<table class="config-table">\n'
    html += '<tr><th>Parameter</th><th>Value</th><th>Description</th></tr>\n'
    for key in CONFIG_DESCRIPTIONS:
        val = palette_cfg.get(key, "—")
        desc = CONFIG_DESCRIPTIONS[key]
        html += f'<tr><td>{key}</td><td>{val}</td><td>{desc}</td></tr>\n'
    html += '</table>\n'
    return html


def render_full_html(sections, palette_cfg, generation_info):
    """Assemble the complete HTML document."""
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hue Ambient — Palette Preview</title>
<style>{CSS}</style>
</head>
<body>
<h1>Hue Ambient — Palette Preview</h1>
<p class="subtitle">{generation_info} &middot; North Vancouver (49.32\u00b0N, 123.07\u00b0W)</p>

<h2>24-Hour Color Timeline</h2>
<p class="note">Hover any segment to see time, sun elevation, and HSB values.</p>
"""
    for section in sections:
        html += section["timeline_html"]

    html += '<h2>Key Moments</h2>\n'
    # Use the first (or only) date's moments
    html += sections[0]["moments_html"]

    html += '<h2>Anchor Points (Base Curve)</h2>\n'
    html += render_anchors_section()

    html += '<h2>Current Configuration</h2>\n'
    html += render_config_section(palette_cfg)

    html += '<p class="note" style="margin-top:40px;">Colors on screen approximate the Hue bulb output — actual bulb colors will differ slightly due to gamut differences.</p>\n'
    html += '</body>\n</html>'
    return html


def main():
    import logging
    logging.disable(logging.CRITICAL)  # suppress palette engine INFO logs

    parser = argparse.ArgumentParser(description="Generate HTML palette visualization")
    parser.add_argument("--date", default=None, help='Date as "YYYY-MM-DD" (default: today)')
    parser.add_argument("--season-compare", action="store_true",
                        help="Show summer solstice, winter solstice, and equinox side-by-side")
    parser.add_argument("--output", default="palette_preview.html", help="Output filename")
    args = parser.parse_args()

    palette_cfg = load_palette_config()

    if args.season_compare:
        today = date.today()
        dates = [
            (date(today.year, 6, 20), "Summer Solstice (Jun 20)"),
            (date(today.year, 3, 20), "Spring Equinox (Mar 20)"),
            (date(today.year, 12, 21), "Winter Solstice (Dec 21)"),
        ]
        gen_info = f"Season comparison — {today.year}"
    elif args.date:
        d = datetime.strptime(args.date, "%Y-%m-%d").date()
        dates = [(d, d.strftime("%A, %B %d, %Y"))]
        gen_info = d.strftime("%A, %B %d, %Y")
    else:
        d = date.today()
        dates = [(d, d.strftime("%A, %B %d, %Y"))]
        gen_info = d.strftime("%A, %B %d, %Y")

    sections = []
    for target_date, label in dates:
        timeline = compute_timeline(target_date, palette_cfg)
        sun_events = get_sun_events(target_date)
        moments = compute_key_moments(target_date, palette_cfg)
        sections.append({
            "timeline_html": render_timeline_section(timeline, sun_events, label),
            "moments_html": render_moments_section(moments),
        })

    html = render_full_html(sections, palette_cfg, gen_info)

    out_path = Path(__file__).parent / args.output
    out_path.write_text(html)
    print(f"Generated: {out_path}")
    print(f"Open in browser: file://{out_path.resolve()}")


if __name__ == "__main__":
    main()
