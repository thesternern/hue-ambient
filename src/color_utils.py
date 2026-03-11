"""
Color space conversion utilities.
HSB (Hue 0-360, Sat 0-100, Bri 0-100) -> RGB (0-255) -> CIE xy
Also: HSB -> Hue API native values (hue 0-65535, sat 0-254, bri 1-254)
"""


def hsb_to_rgb(hue_deg: float, sat_pct: float, bri_pct: float) -> tuple[int, int, int]:
    """Convert HSB (H:0-360, S:0-100, B:0-100) to RGB (0-255 each)."""
    h = hue_deg % 360
    s = sat_pct / 100.0
    v = bri_pct / 100.0

    if s == 0:
        c = int(v * 255)
        return c, c, c

    h_sector = h / 60.0
    i = int(h_sector)
    f = h_sector - i
    p = v * (1 - s)
    q = v * (1 - s * f)
    t = v * (1 - s * (1 - f))

    sectors = [
        (v, t, p), (q, v, p), (p, v, t),
        (p, q, v), (t, p, v), (v, p, q),
    ]
    r, g, b = sectors[i % 6]
    return int(r * 255), int(g * 255), int(b * 255)


def _linearize(c: float) -> float:
    """sRGB gamma to linear."""
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def rgb_to_xy(r: int, g: int, b: int) -> tuple[float, float]:
    """Convert RGB (0-255) to CIE xy chromaticity (Philips Hue wide gamut D65)."""
    r_lin = _linearize(r / 255.0)
    g_lin = _linearize(g / 255.0)
    b_lin = _linearize(b / 255.0)

    # Wide color gamut D65
    X = r_lin * 0.664511 + g_lin * 0.154324 + b_lin * 0.162028
    Y = r_lin * 0.283881 + g_lin * 0.668433 + b_lin * 0.047685
    Z = r_lin * 0.000088 + g_lin * 0.072310 + b_lin * 0.986039

    total = X + Y + Z
    if total == 0:
        return 0.0, 0.0
    return round(X / total, 4), round(Y / total, 4)


def hsb_to_hue_api(hue_deg: float, sat_pct: float, bri_pct: float) -> tuple[int, int, int]:
    """Convert HSB to Hue API native integers: hue (0-65535), sat (0-254), bri (1-254)."""
    hue_val = int((hue_deg % 360) / 360.0 * 65535)
    sat_val = int(min(sat_pct, 100) / 100.0 * 254)
    bri_val = max(1, int(min(bri_pct, 100) / 100.0 * 254))
    return hue_val, sat_val, bri_val
