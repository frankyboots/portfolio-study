"""The locked matplotlib style for every figure export (AD-11).

One canvas, one stylesheet, one set of tokens: every figure builder
calls :func:`apply_style` before touching a figure and takes every
color from the pairings contract — figure code never carries a hex
literal. The stylesheet locks

* the canonical export canvas (1200 x 800 px; 5in wide x 800/240 in
  tall at the locked 240 dpi — 240 dpi is what keeps the locked 2pt
  dash ladder at the 2 display-px series-line floor),
* the vendored fonts (``config/fonts``; never system fonts),
* the paper ground and ink/rule/accent tokens,
* ``svg.fonttype = path`` plus the pinned ``svg.hashsalt`` so SVG
  exports are self-contained and byte-stable.

The dash/weight ladder and the hatch library are the DESIGN.md
locked sets; builders pick from them, they do not invent.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import matplotlib

#: Repo root: analysis/figures/style.py -> analysis/figures -> analysis -> root.
ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "config" / "pairings_contract.json"
FONT_DIR = ROOT / "config" / "fonts"

#: Canonical export canvas in render px (DESIGN.md canonical export
#: geometry: 1200px wide; height per chart, locked in the stylesheet --
#: the pilot locks 800px, enough for the stamp band + label band).
CANVAS_PX: tuple[int, int] = (1200, 800)
FIGSIZE_IN: tuple[float, float] = (5.0, CANVAS_PX[1] / 240.0)
DPI: int = 240

#: 2 canvas px on the 1200px canonical export, in display px.
CANVAS_TO_DISPLAY: float = 375.0 / CANVAS_PX[0]  # 0.3125

#: The release-stamp keep-out rect on the 1200x800 canvas: any byte
#: (SVG group / PNG pixel) inside (x0, y0, x1, y1) is legitimately
#: stamp bytes -- the BUILD-HEAD leg differs between builds by design
#: (gate 7 strips it; the pipeline's churn rule ignores it). Top-left
#: band; the four rendered stamp lines and their border live here.
STAMP_RECT_PX: tuple[int, int, int, int] = (24, 24, 480, 270)

#: DESIGN.md release-stamp treatment.
STAMP_ROTATION_DEG: float = -2.0
STAMP_PAD_Y_PX: float = 2.0
STAMP_PAD_X_PX: float = 9.0
STAMP_BORDER_PX: float = 2.0  # "2px solid accent-red border"

#: Locked line dash/weight ladder (DESIGN.md series-encoding ladder):
#: name -> (matplotlib dash style, weight in pt at the locked DPI).
DASH_LADDER: dict[str, tuple[str, float]] = {
    "dash-dot": ("-.", 2.0),
    "dashed": ("--", 2.0),
    "dotted": (":", 2.0),
    "solid": ("-", 2.5),
}

#: Locked hatch library (DESIGN.md): the closed set, mapped to
#: matplotlib hatch strings. ``double-bar`` is the double-vertical
#: pattern (DESIGN's "‖").
HATCH_LIBRARY: dict[str, str] = {
    "backslash": "\\",
    "cross": "x",
    "dots": "o",
    "double-bar": "||",
    "slash": "/",
}
HATCH_MIN_PITCH_PX: float = 8.0  # at the 1200px render
HATCH_LINWIDTH_PX: float = 2.0  # >= 1.5px hatch linewidth, locked at 2

#: The one hash salt for every SVG export (mirrors config/matplotlibrc
#: and scripts/pipeline.py SVG_HASHSALT).
SVG_HASHSALT: str = "portfolio-study-v1"

#: Vendored chart fonts (AD-11): chart interiors in Source Serif 4,
#: data-bearing microcopy and stamps in IBM Plex Mono.
SERIF_FAMILY: str = "Source Serif 4"
MONO_FAMILY: str = "IBM Plex Mono"
VENDORED_FONTS: dict[str, str] = {
    "SourceSerif4-Bold.ttf": "bold",
    "SourceSerif4-Regular.ttf": "regular",
    "IBMPlexMono-Regular.ttf": "mono",
}

#: Stamp family list: Plex Mono carries the ASCII stamp runs; U+25AE
#: (the stamp block) is absent from both chart faces, so DejaVu Sans
#: (bundled with matplotlib, never a system font) provides it.
MONO_FAMILY_LIST: list[str] = [MONO_FAMILY, "DejaVu Sans"]


@lru_cache(maxsize=1)
def load_contract() -> dict:
    """Load the pairings contract (grounds, tokens, pairings rows)."""
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def token(name: str) -> str:
    """The hex value of a contract token (grounds and tokens both)."""
    contract = load_contract()
    for table in (contract.get("tokens", {}), contract.get("grounds", {})):
        if name in table:
            return str(table[name])
    raise KeyError(f"unknown contract token: {name!r}")


def pairing_row(fg: str, on: str) -> dict | None:
    """The contract pairing row for (fg, on), or None when absent.

    An absent pairing is a gate-4 failure upstream of this call; the
    builders treat None as an error and never fall back to a color.
    """
    for row in load_contract().get("pairings", ()):  # type: ignore[union-attr]
        if row.get("fg") == fg and row.get("on") == on:
            return row
    return None


def dash_style(name: str) -> tuple[str, float]:
    """The locked ladder entry for a dash name."""
    if name not in DASH_LADDER:
        raise KeyError(f"dash not in the locked ladder: {name!r}")
    return DASH_LADDER[name]


def hatch(name: str) -> str:
    """The matplotlib hatch string for a locked hatch-library name."""
    if name not in HATCH_LIBRARY:
        raise KeyError(f"hatch not in the locked library: {name!r}")
    return HATCH_LIBRARY[name]


def ensure_vendored_fonts() -> None:
    """Register the vendored TTFs with the font manager (idempotent).

    Matplotlib discovers no other fonts for the chart families: the
    rcParams below point at these names, which resolve only to the
    files under ``config/fonts``.
    """
    from matplotlib import font_manager

    for filename in VENDORED_FONTS:
        path = FONT_DIR / filename
        if not path.is_file():
            raise FileNotFoundError(f"missing vendored font: {path}")
        for known in font_manager.fontManager.ttflist:
            if known.fname == str(path):
                break
        else:
            font_manager.fontManager.addfont(str(path))


def apply_style() -> None:
    """Lock the full rcParam set for a figure build.

    Idempotent; every builder calls it before creating any figure. All
    colors come from the pairings contract (no hex literals here or in
    any figure code).
    """
    ensure_vendored_fonts()
    rc = matplotlib.rcParams
    paper = token("paper")
    ink = token("ink")
    rule = token("rule")
    rc.update(
        {
            # canvas
            "figure.figsize": FIGSIZE_IN,
            "figure.dpi": DPI,
            "figure.facecolor": paper,
            "savefig.facecolor": paper,
            # svg: self-contained, byte-stable
            "svg.fonttype": "path",
            "svg.hashsalt": SVG_HASHSALT,
            # fonts: the vendored faces only
            "font.family": "serif",
            "font.serif": [SERIF_FAMILY],
            "font.size": 13.0,  # tick labels: caption-class (>=13 display px)
            "mathtext.fontset": "stix",  # not used by the locked figures; pinned anyway
            # ink and rules
            "text.color": ink,
            "xtick.color": ink,
            "ytick.color": ink,
            "axes.edgecolor": rule,
            "axes.facecolor": paper,
            "axes.linewidth": 0.75,  # hairline spines: 2.5 canvas px
            "axes.labelcolor": ink,
            "axes.labelsize": 14.0,  # axis titles: caption-class
            "axes.axisbelow": True,
            "grid.color": rule,
            "grid.linewidth": 0.5,  # light horizontal gridlines: 1.67 canvas px
            # determinism
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )
    # Builders enable gridlines per-axes, y-only (DESIGN.md sparse grid):
    # the rc default leaves the global grid off.


def measure_text_px(text) -> float:
    """The rendered height of a text artist, in canvas px.

    Measures the real renderer extent (``get_window_extent`` on the
    active backend's renderer), never a declared constant: the value
    moves with the artist's font size and content, and gate 4 checks
    it against the display-px floors. Rotation-aware layout guards
    (canvas-escape, y-title/stamp collision) use this function.
    """
    renderer = text.figure.canvas.get_renderer()
    return float(text.get_window_extent(renderer).height)


def measure_text_glyph_px(text) -> float:
    """The font-glyph height of a text artist, in canvas px.

    ``measure_text_px`` on a rotated label returns the string's
    *width* (the rotated extent's height), which would let a
    caption-class floor pass on the wrong dimension. Measure on the
    same live artist at rotation 0, restoring the artist's rotation
    afterward: a single-line extent height proportional to font size,
    the same basis as the tick-label probe.
    """
    renderer = text.figure.canvas.get_renderer()
    rotation = text.get_rotation()
    text.set_rotation(0.0)
    try:
        return float(text.get_window_extent(renderer).height)
    finally:
        text.set_rotation(rotation)


def measure_line_px(line) -> float:
    """The rendered stroke width of a line artist, in canvas px."""
    return float(line.get_linewidth()) * DPI / 72.0


def canvas_px_of_pt(pt: float) -> float:
    """Point size at the locked DPI, in canvas px."""
    return pt * DPI / 72.0
