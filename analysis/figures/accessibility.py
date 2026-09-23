"""WCAG 2.x contrast math and the phone-legibility floors for gate 4.

Pure functions over the pairings contract and the figure records:
the gate re-derives every contrast ratio from the contract's hex
values (the recorded ratio is a spot-check, not the source of truth)
and checks every recorded measurement against the display-px floors.

Display-px is the phone-legibility unit: the canonical export canvas
is 1200px wide and displays at 375px logical width, so

    display_px = render_px * 375 / 1200

Role thresholds are the WCAG-AA floors per contract role; the
per-element floors below are the DESIGN.md phone-width minimums
applied to the 375px re-raster of a 1200px canonical export.
"""

from __future__ import annotations

#: WCAG-AA contrast floor per contract role. ``decorative`` is exempt
#: by role (it carries no information), not by waiver.
ROLE_THRESHOLDS: dict[str, float] = {
    "data-series": 3.0,
    "decorative": 0.0,
    "non-text": 3.0,
    "text-large": 3.0,
    "text-normal": 4.5,
}

#: Canonical export width and the 375px logical display width.
CANONICAL_CANVAS_PX = 1200
DISPLAY_WIDTH_PX = 375
DISPLAY_SCALE = DISPLAY_WIDTH_PX / CANONICAL_CANVAS_PX  # 0.3125

#: Phone-legibility floors in display px, keyed by the record's
#: measurement class.
FLOOR_DISPLAY_PX: dict[str, float] = {
    "caption-class": 13.0,
    "mono-stamp": 11.0,
    "series-label": 11.0,
    "series-line": 2.0,
}

#: A text element declared for a ``text-large`` role must additionally
#: be recorded at >= 14 display px (the ">=14px only" clause).
TEXT_LARGE_DISPLAY_PX = 14.0

#: Grayscale-survival: two data hues whose WCAG relative luminance
#: differs by less than this must be distinguished by a declared
#: different dash (DESIGN.md series-encoding ladder; EXPERIENCE.md
#: grayscale check).
GRAYSCALE_DL_MAX = 0.02


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    """``'#rrggbb'`` -> ``(r, g, b)``. Fails loudly on malformed input."""
    if not isinstance(value, str) or len(value) != 7 or value[0] != "#":
        raise ValueError(f"not a #rrggbb hex color: {value!r}")
    digits = value[1:]
    if any(c not in "0123456789abcdefABCDEF" for c in digits):
        raise ValueError(f"not a #rrggbb hex color: {value!r}")
    return tuple(int(digits[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def relative_luminance(rgb: tuple[int, int, int]) -> float:
    """WCAG 2.x relative luminance of an sRGB triple."""

    def channel(c: int) -> float:
        s = c / 255.0
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg_hex: str, bg_hex: str) -> float:
    """WCAG 2.x contrast ratio of a foreground on a background."""
    lf = relative_luminance(hex_to_rgb(fg_hex))
    lb = relative_luminance(hex_to_rgb(bg_hex))
    hi, lo = max(lf, lb), min(lf, lb)
    return (hi + 0.05) / (lo + 0.05)


def display_px(render_px: float) -> float:
    """Render (canvas-scale) pixels at the 1200px export -> 375px display px."""
    return render_px * DISPLAY_SCALE


def role_threshold(role: str) -> float:
    """The contrast floor a role claims; unknown roles fail in the gate."""
    if role not in ROLE_THRESHOLDS:
        raise KeyError(f"unknown contract role: {role!r}")
    return ROLE_THRESHOLDS[role]
