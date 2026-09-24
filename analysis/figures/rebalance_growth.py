"""Pilot figure: rebalance_growth_v1 — monthly vs annual rebalanced REAL 60/40.

The story-1.6 end-to-end proof: one locked-style figure built from the
two registered series artifacts (the monthly-rebalanced canonical series
as the primary, the annual-rebalanced comparator as the baseline),
exported to PNG + SVG with the baked release stamp and one
deterministic ``*.figure.json`` record.

Data is read straight from the registered CSVs under
``artifacts/series/`` — no .xls, no series arithmetic, no hard-coded
numbers: every value the figure shows (lines, labels, alt text,
extremes) is computed from the artifacts. The two series share the
data-good / data-neutral pair, whose relative-luminance delta
(0.0125) is below the 0.02 grayscale threshold, so line identity is
carried by the locked dash ladder (solid primary / dashed baseline),
never by hue alone.

Layout (1200x800 canvas): top-left keep-out band holds the compact
four-line release stamp; the two swatch-keyed direct labels sit in
the top-right band, each a label with a short line-style swatch in
its series' own stroke beside it (DESIGN.md: labels are mandatory,
the swatch carries the series identity, no leader rules). The axes
occupy the lower region; guards on the measured extents check that no
label overlaps the other label, that labels and swatches clear the
stamp keep-out band, and that no swatch crosses the other label.
"""

from __future__ import annotations

import io
import math
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import Polygon

from analysis.figures import _records, style

NAME = "rebalance_growth_v1"
SCRIPT_REL = "analysis/figures/rebalance_growth.py"

#: The two registered inputs, primary artifact first (mirrors SERIES).
SOURCE_ARTIFACTS = (
    "canonical_60_40_monthly_v1",
    "canonical_60_40_annual_v1",
)

UNITS = "growth index, decimal (base 1.0 at 1871.01)"

#: Declaration order: primary first (the finding), baseline second.
SERIES = (
    {
        "dash": "solid",
        "display_name": "Monthly-rebalanced 60/40, real",
        "fg": "data-good",
        "id": "monthly_rebalanced_real",
        "on": "paper",
        "role": "primary",
    },
    {
        "dash": "dashed",
        "display_name": "Annual-rebalanced 60/40, real",
        "fg": "data-neutral",
        "id": "annual_rebalanced_real",
        "on": "paper",
        "role": "baseline",
    },
)

X_LABEL = "Year"
# Y-axis title: short enough that its rotated extent clears the
# top-left stamp block (the base-month precision lives in the
# alt-text, not the axis title).
Y_LABEL = "Real growth index"

#: Locked layout fractions (the 1200x800 pilot canvas): left 174px,
#: bottom 172px, right 1182px, top 510px from the bottom (290px from the
#: top edge), leaving the top band for the stamp + direct labels.
AX_FRACTIONS = {"left": 0.145, "bottom": 0.215, "right": 0.985, "top": 0.6375}

#: x/y plot ranges (log y).
X_MIN, X_MAX = 1870.0, 2030.0
Y_MIN, Y_MAX = 1.0, 10.0**4.08

#: Swatch-keyed direct labels: figure-fraction anchor (ha=right,
#: va=center) for the label text; the short line-style swatch sits in the
#: series' own stroke to the left of the measured label extent
#: (the swatch carries the series->label association; no leaders).
LABEL_ANCHORS: dict[str, tuple[float, float]] = {
    "annual_rebalanced_real": (1160.0 / 1200.0, 1.0 - 95.0 / 800.0),
    "monthly_rebalanced_real": (1105.0 / 1200.0, 1.0 - 170.0 / 800.0),
}
SWATCH_LEN_PX = 40.0
SWATCH_GAP_PX = 12.0

STAMP_ANCHOR_PX = (48.0, 44.0)


def _parse_dates(decimals: pd.Series) -> pd.Series:
    """Decimal YYYY.MM index -> plot x in calendar years.

    The dataset encodes the month as ``round((date - year) * 100)``
    with calendar month codes (DATA.md §2: 1871.01 = January 1871, so
    the decimal value 1871.1 ≡ 1871.10 = October): plot x is the
    calendar year plus the month's fractional position in the year.
    """
    years = decimals.astype(float).astype(int)
    months = (
        (decimals - years).apply(lambda dt: round((dt - int(dt)) * 100)).clip(1, 12)
    )
    return years + (months - 1) / 12.0


MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def _humanize_ym(token: str) -> str:
    """Native ``YYYY.MM`` token -> "Month YYYY" prose (alt-text voice).

    String split plus the month-name table, never float arithmetic:
    the dataset encodes months as decimal codes and a float parse
    regressed here before. Structured fields (``range``) keep the
    native tokens; only the prose layer humanizes.
    """
    year, _, month = token.partition(".")
    return f"{MONTH_NAMES[int(month) - 1]} {year}"


def _fmt(value: float) -> str:
    """Display formatting for alt-text numbers: 4 significant figures."""
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    if abs(value) >= 10:
        return f"{value:,.1f}"
    if abs(value) >= 1:
        return f"{value:,.2f}"
    return f"{value:.3f}"


def _load_series(root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for artifact in SOURCE_ARTIFACTS:
        path = root / "artifacts" / "series" / f"{artifact}.csv"
        if not path.is_file():
            raise FileNotFoundError(
                f"missing source artifact {path.relative_to(root)} "
                "(run the series/comparator stages first)"
            )
        frame = pd.read_csv(path)
        if list(frame.columns) != ["date", "real", "nominal"]:
            raise ValueError(f"unexpected series CSV columns: {list(frame.columns)}")
        frames[artifact] = frame
    annual = frames["canonical_60_40_annual_v1"]
    monthly = frames["canonical_60_40_monthly_v1"]
    if not monthly["date"].equals(annual["date"]):
        raise ValueError("the two source artifacts do not share the same date index")
    return annual, monthly


def _alt_text(annual: pd.DataFrame, monthly: pd.DataFrame) -> dict:
    """The EXPERIENCE.md v1 alt-text record, computed from the artifacts."""
    start = str(annual["date"].iloc[0])
    end = str(annual["date"].iloc[-1])
    start_h, end_h = _humanize_ym(start), _humanize_ym(end)

    a_end, m_end = float(annual["real"].iloc[-1]), float(monthly["real"].iloc[-1])
    # The "(both series)" claim is checked against BOTH series: the sets
    # of sub-1.0 readings must agree, or the build fails loudly rather
    # than emit a false alt-text sentence.
    sub_a = set(annual.loc[annual["real"] < 1.0, "date"].astype(str))
    sub_m = set(monthly.loc[monthly["real"] < 1.0, "date"].astype(str))
    if sub_a != sub_m:
        raise AssertionError(
            "sub-1.0 readings diverge between the two series "
            f"(annual-only: {sorted(sub_a - sub_m)}, "
            f"monthly-only: {sorted(sub_m - sub_a)}); the '(both series)' claim "
            "would be false"
        )
    if sub_a:
        sub1 = annual[annual["real"] < 1.0]
        sub1_pts = ", ".join(
            f"{_fmt(float(v))} at {_humanize_ym(str(d))}"
            for d, v in zip(sub1["date"], sub1["real"])
        )
        sub1_sentence = f"the only sub-1.0 index readings are {sub1_pts} (both series)"
    else:
        sub1_sentence = "no sub-1.0 index readings"
    extremes = (
        f"Extremes: {sub1_sentence}; the span maxima are the terminal values — "
        f"annual {_fmt(a_end)}, monthly {_fmt(m_end)} at {end_h}."
    )
    trend = (
        f"Annual-rebalanced real 60/40 grows from "
        f"{_fmt(float(annual['real'].iloc[0]))} at {start_h} to {_fmt(a_end)} at "
        f"{end_h}; monthly-rebalanced grows from "
        f"{_fmt(float(monthly['real'].iloc[0]))} to {_fmt(m_end)} over the same "
        f"span, so annual rebalancing ends {_fmt(a_end - m_end)} index points "
        "above monthly."
    )
    alt_text = (
        f"Line chart of 2 real 60/40 growth-index series "
        f"(annual- and monthly-rebalanced), {start_h} to {end_h}. "
        f"Axes: {X_LABEL}, {Y_LABEL} (log scale). {trend} {extremes} "
        f"2 series: monthly-rebalanced (primary, solid) and "
        f"annual-rebalanced (baseline, dashed)."
    )
    return {
        "alt_text": alt_text,
        "axis": {"scale": "log", "x_label": X_LABEL, "y_label": Y_LABEL},
        "chart_type": "line",
        "extremes": extremes,
        "pairing_applies": False,
        "range": {"end": end, "period": "monthly", "start": start},
        "series": [
            {
                "display_name": spec["display_name"],
                "id": spec["id"],
                "role": spec["role"],
                "units": UNITS,
            }
            for spec in SERIES
        ],
        "trend": trend,
    }


def _stamp_lines(stamp: str, script: str) -> list[str]:
    """Split the one-line schema stamp into the compact corner block.

    The record's ``stamp`` field keeps the canonical one-line string
    (gate 7's regex validates it); the render wraps it into short
    lines so the block stays a compact top-left corner.
    """
    head = stamp.split(" · ")[0] + " ·"
    build = stamp.split(" · ")[1].split(" · ")[0]
    parts = script.rsplit("/", 1)
    path_lines = [parts[0] + "/", parts[1]] if len(parts) == 2 else [script]
    return [head, build, *path_lines]


def _add_stamp(
    fig: plt.Figure,
    stamp: str,
    script: str,
    anchor_px: tuple[float, float] = STAMP_ANCHOR_PX,
) -> tuple[plt.Text, Polygon]:
    """The release stamp: compact block, mono, -2deg, inside STAMP_RECT_PX.

    The frame is drawn from corners BAKED into figure-fraction
    coordinates: the -2deg rotation about the top-left anchor is applied
    in y-up display px at the locked canvas dpi up front, so Agg (PNG)
    and the SVG backend render byte-consistent geometry instead of
    relying on a backend-dependent transform chain.

    ``anchor_px`` is the top-left text anchor in canvas px (y-down from
    the top); the default is the pilot's locked corner anchor, so the
    pilot's bytes are unchanged — the hero builder passes its own
    anchor to make room for its computed episode-count line above the
    stamped block.
    """
    x0, y0, x1, y1 = style.STAMP_RECT_PX
    width, height = style.CANVAS_PX
    anchor_x, anchor_y = anchor_px

    text = fig.text(
        anchor_x / width,
        1.0 - anchor_y / height,
        "\n".join(_stamp_lines(stamp, script)),
        family=style.MONO_FAMILY_LIST,
        size=10.0,
        color=style.token("accent-red"),
        ha="left",
        va="top",
        rotation=style.STAMP_ROTATION_DEG,
        rotation_mode="anchor",
        gid="release-stamp",
    )
    # The active canvas's renderer; text extents are figure-dpi-scaled,
    # so the measured values are backend-invariant (the envelope pins Agg).
    renderer = fig.canvas.get_renderer()  # type: ignore[attr-defined]
    extent = text.get_window_extent(renderer)
    pad_x, pad_y = style.STAMP_PAD_X_PX, style.STAMP_PAD_Y_PX
    box_left = float(extent.x0) - pad_x
    box_bottom = float(extent.y0) - pad_y  # y-up display px (origin bottom-left)
    box_width = float(extent.width) + 2.0 * pad_x
    box_height = float(extent.height) + 2.0 * pad_y

    # Bake the rotation into the frame corners, at the locked canvas dpi:
    # rotate the padded box -2deg about the text anchor in y-up display px
    # (matplotlib's rotation convention), then draw a plain Polygon in
    # figure fractions, so Agg (PNG) and the SVG backend render
    # byte-consistent geometry.
    theta = math.radians(style.STAMP_ROTATION_DEG)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    anchor_display = (anchor_x, height - anchor_y)  # y-up display px
    corners_display = []
    for cx, cy in (
        (box_left, box_bottom),
        (box_left + box_width, box_bottom),
        (box_left + box_width, box_bottom + box_height),
        (box_left, box_bottom + box_height),
    ):
        dx, dy = cx - anchor_display[0], cy - anchor_display[1]
        corners_display.append(
            (
                anchor_display[0] + dx * cos_t - dy * sin_t,
                anchor_display[1] + dx * sin_t + dy * cos_t,
            )
        )
    frame = Polygon(
        [(x / width, y / height) for x, y in corners_display],
        closed=True,
        transform=fig.transFigure,
        fill=False,
        edgecolor=style.token("accent-red"),
        linewidth=style.STAMP_BORDER_PX * 72.0 / style.DPI,  # 2 canvas px
        gid="release-stamp-frame",
    )
    fig.add_artist(frame)

    # Keep-out check on the same baked corners the frame is drawn from,
    # in canvas px (y-down from the top): all four sides of
    # STAMP_RECT_PX, plus the canvas bounds. The stamp's -2deg rotation
    # about the top-left anchor swings the other corners; the worst of
    # them must stay inside the band.
    corners_canvas = [(x, height - y) for x, y in corners_display]  # y-down px
    worst = {
        "left": min(x for x, _ in corners_canvas),
        "top": min(y for _, y in corners_canvas),
        "right": max(x for x, _ in corners_canvas),
        "bottom": max(y for _, y in corners_canvas),
    }
    if (
        worst["left"] < x0
        or worst["top"] < y0
        or worst["right"] > x1
        or worst["bottom"] > y1
        or worst["left"] < 0.0
        or worst["top"] < 0.0
        or worst["right"] > width
        or worst["bottom"] > height
    ):
        raise AssertionError(
            f"stamp frame escapes STAMP_RECT_PX {style.STAMP_RECT_PX} "
            f"or the canvas {width}x{height}: left {worst['left']:.1f} "
            f"(min {x0}), top {worst['top']:.1f} (min {y0}), "
            f"right {worst['right']:.1f} (max {x1}), bottom {worst['bottom']:.1f} "
            f"(max {y1})"
        )
    return text, frame


def _rects_overlap(a, b, gap: float = 2.0) -> bool:
    return not (
        a.x1 + gap <= b.x0
        or b.x1 + gap <= a.x0
        or a.y1 + gap <= b.y0
        or b.y1 + gap <= a.y0
    )


def build_figure(root: Path) -> int:
    """Build, export, and record the pilot figure under ``root``.

    Writes ``artifacts/figures/rebalance_growth_v1.{png,svg}`` and its
    ``.figure.json`` record; returns 0 on success. Layout violations
    (the keep-out and overlap guards) raise AssertionError instead of
    returning a non-zero exit code.
    """
    style.apply_style()
    annual, monthly = _load_series(root)
    x_a = _parse_dates(annual["date"])
    x_m = _parse_dates(monthly["date"])
    v_a = annual["real"]
    v_m = monthly["real"]

    fig, ax = plt.subplots(figsize=style.FIGSIZE_IN, facecolor=style.token("paper"))
    fig.subplots_adjust(**AX_FRACTIONS)
    ax.set_facecolor(style.token("paper"))
    ax.grid(axis="y", color=style.token("rule"), linewidth=0.5)

    # The plotted data per series id (the role/dash/fg assignment comes
    # from SERIES; the data binding stays explicit, not role-keyed).
    data: dict[str, tuple[pd.Series, pd.Series]] = {
        "annual_rebalanced_real": (x_a, v_a),
        "monthly_rebalanced_real": (x_m, v_m),
    }
    artists: dict[str, plt.Line2D] = {}
    for spec in SERIES:
        dash, lw_pt = style.dash_style(spec["dash"])
        xs, vals = data[spec["id"]]
        artists[spec["id"]] = ax.plot(
            xs,
            vals,
            color=style.token(spec["fg"]),
            linestyle=dash,
            linewidth=lw_pt,
            label=spec["display_name"],
            solid_capstyle="butt",
            dash_capstyle="butt",
        )[0]

    ax.set_yscale("log")
    ax.set_xlim(X_MIN, X_MAX)
    ax.set_ylim(Y_MIN, Y_MAX)
    # Both axis titles pinned to the tick-label 13 pt caption-class
    # basis (the x title would otherwise inherit rc axes.labelsize
    # 14.0); the axis_titles record is measured on the glyph basis.
    ax.set_xlabel(X_LABEL, size=13.0)
    ax.set_ylabel(Y_LABEL, size=13.0)
    ax.tick_params(axis="both", which="major", labelsize=13.0)
    for spine in ax.spines.values():
        spine.set_edgecolor(style.token("rule"))
        spine.set_linewidth(0.75)
    # DESIGN.md register: hairline axes, no panel borders. The rc set
    # carries no spine-visibility entry, so the per-axes loop is the
    # pin point (Epic 2 may lift this into style.apply_style).
    for spine_name in ("top", "right"):
        ax.spines[spine_name].set_visible(False)

    # Swatch-keyed direct labels in the top-right band (fig
    # fractions): the label text carries the series display name; the
    # short line-style swatch in the series' own stroke sits beside it
    # (no leader rules — the swatch carries the association).
    labels: dict[str, plt.Text] = {}
    for spec in SERIES:
        fx, fy = LABEL_ANCHORS[spec["id"]]
        labels[spec["id"]] = fig.text(
            fx,
            fy,
            spec["display_name"],
            family=style.SERIF_FAMILY,
            size=11.0,
            color=style.token(spec["fg"]),
            ha="right",
            va="center",
        )
    h_px = style.CANVAS_PX[1]
    w_px = style.CANVAS_PX[0]
    axis_top_display = AX_FRACTIONS["top"] * h_px
    renderer = fig.canvas.get_renderer()  # type: ignore[attr-defined]

    # The swatch: a short sample of the series line's own stroke, left
    # of the measured label extent, at the label's vertical center.
    swatches: dict[str, plt.Line2D] = {}
    for spec in SERIES:
        sid = spec["id"]
        ext = labels[sid].get_window_extent(renderer)
        swatch_right_px = float(ext.x0) - SWATCH_GAP_PX
        swatch_left_px = swatch_right_px - SWATCH_LEN_PX
        if swatch_left_px < style.STAMP_RECT_PX[2] + 5:
            raise AssertionError(f"swatch {sid} intrudes on the stamp band")
        dash, lw_pt = style.dash_style(spec["dash"])
        y_center_display = (float(ext.y0) + float(ext.y1)) / 2.0
        swatches[sid] = plt.Line2D(
            [swatch_left_px / w_px, swatch_right_px / w_px],
            [y_center_display / h_px, y_center_display / h_px],
            transform=fig.transFigure,
            color=style.token(spec["fg"]),
            linestyle=dash,
            linewidth=lw_pt,
            solid_capstyle="butt",
            dash_capstyle="butt",
        )
        fig.add_artist(swatches[sid])

    stamp = _records.stamp_string(
        _records.resolve_vintage(root),
        _records.resolve_build_head(root),
        SCRIPT_REL,
    )
    stamp_text, _stamp_border = _add_stamp(fig, stamp, SCRIPT_REL)

    # One forced draw lays out every real artist (ticks included); the
    # recorded measurements are then the real renderer extents, not
    # declared constants.
    renderer = fig.canvas.get_renderer()  # type: ignore[attr-defined]
    fig.draw(renderer)

    # Layout guards, all from measured extents: labels clear the stamp
    # keep-out band and stay in the top band above the axes; labels
    # never overlap; no swatch crosses the other label; the axis
    # titles fit inside the canvas.
    for i, spec in enumerate(SERIES):
        sid = spec["id"]
        ext = labels[sid].get_window_extent(renderer)
        if float(ext.x0) < style.STAMP_RECT_PX[2] + 5:
            raise AssertionError(f"label {sid} intrudes on the stamp band")
        if float(ext.y0) < axis_top_display + 2.0:
            raise AssertionError(f"label {sid} sinks below the axes top")
        other = SERIES[(i + 1) % len(SERIES)]["id"]
        other_ext = labels[other].get_window_extent(renderer)
        if _rects_overlap(ext, other_ext):
            raise AssertionError(f"labels {sid} and {other} overlap")
        swatch_ext = swatches[sid].get_window_extent(renderer)
        if _rects_overlap(swatch_ext, other_ext):
            raise AssertionError(f"swatch {sid} crosses label {other}")
    ylabel_ext = ax.yaxis.get_label().get_window_extent(renderer)
    xlabel_ext = ax.xaxis.get_label().get_window_extent(renderer)
    for name, ext in (("y title", ylabel_ext), ("x title", xlabel_ext)):
        if (
            float(ext.x0) < 0.0
            or float(ext.y0) < 0.0
            or float(ext.x1) > style.CANVAS_PX[0]
            or float(ext.y1) > style.CANVAS_PX[1]
        ):
            raise AssertionError(f"{name} escapes the canvas")
    # The rotated y title must clear the stamp block (top-left band).
    sx0, _, sx1, sy1 = style.STAMP_RECT_PX
    stamp_bottom_display = style.CANVAS_PX[1] - sy1
    if (
        float(ylabel_ext.y1) > stamp_bottom_display - 8.0
        and float(ylabel_ext.x1) > sx0
        and float(ylabel_ext.x0) < sx1
    ):
        raise AssertionError("y title collides with the stamp block")

    tick_probe = ax.get_xticklabels()[1]
    label_px = {
        spec["id"]: style.measure_text_px(labels[spec["id"]]) for spec in SERIES
    }
    tick_px = style.measure_text_px(tick_probe)
    # Glyph basis (rotation 0): the record must carry the font height,
    # not the rotated string's width, so gate 4's caption-class floor
    # judges the right dimension for both titles.
    title_px = max(
        style.measure_text_glyph_px(ax.xaxis.get_label()),
        style.measure_text_glyph_px(ax.yaxis.get_label()),
    )
    # The stamp's legibility is its per-line height (the block is a
    # fixed four-line corner render of the one-line record string).
    stamp_px = style.measure_text_px(stamp_text) / len(_stamp_lines(stamp, SCRIPT_REL))

    record = {
        "alt_text": _alt_text(annual, monthly),
        "builder": SCRIPT_REL,
        "canvas_px": {"height": style.CANVAS_PX[1], "width": style.CANVAS_PX[0]},
        "measurements": [
            {
                "class": "series-line",
                "element": f"series_line_{spec['id']}",
                "render_px": style.measure_line_px(artists[spec["id"]]),
                "display_px": style.measure_line_px(artists[spec["id"]])
                * style.CANVAS_TO_DISPLAY,
            }
            for spec in SERIES
        ]
        + [
            {
                "class": "series-label",
                "element": f"direct_label_{spec['id']}",
                "render_px": label_px[spec["id"]],
                "display_px": label_px[spec["id"]] * style.CANVAS_TO_DISPLAY,
            }
            for spec in SERIES
        ]
        + [
            {
                "class": "series-line",
                "element": f"label_swatch_{spec['id']}",
                "render_px": style.measure_line_px(swatches[spec["id"]]),
                "display_px": style.measure_line_px(swatches[spec["id"]])
                * style.CANVAS_TO_DISPLAY,
            }
            for spec in SERIES
        ]
        + [
            {
                "class": "caption-class",
                "element": "tick_labels",
                "render_px": tick_px,
                "display_px": tick_px * style.CANVAS_TO_DISPLAY,
            },
            {
                "class": "caption-class",
                "element": "axis_titles",
                "render_px": title_px,
                "display_px": title_px * style.CANVAS_TO_DISPLAY,
            },
            {
                "class": "mono-stamp",
                "element": "stamp_text",
                "render_px": stamp_px,
                "display_px": stamp_px * style.CANVAS_TO_DISPLAY,
            },
            {
                "class": "hairline",
                "element": "gridlines",
                "render_px": style.canvas_px_of_pt(0.5),
                "display_px": style.canvas_px_of_pt(0.5) * style.CANVAS_TO_DISPLAY,
            },
            {
                "class": "hairline",
                "element": "spines",
                "render_px": style.canvas_px_of_pt(0.75),
                "display_px": style.canvas_px_of_pt(0.75) * style.CANVAS_TO_DISPLAY,
            },
            {
                "class": "hairline",
                "element": "stamp_border",
                "render_px": style.STAMP_BORDER_PX,
                "display_px": style.STAMP_BORDER_PX * style.CANVAS_TO_DISPLAY,
            },
        ],
        "name": NAME,
        "series": [
            {
                "dash": spec["dash"],
                "display_name": spec["display_name"],
                "fg": spec["fg"],
                "id": spec["id"],
                "on": spec["on"],
                "role": spec["role"],
                "units": UNITS,
            }
            for spec in SERIES
        ],
        "source_artifacts": list(SOURCE_ARTIFACTS),
        "stamp": stamp,
        "style_declarations": [
            {
                "element": "series_line",
                "fg": spec["fg"],
                "on": spec["on"],
                "role": "data-series",
            }
            for spec in SERIES
        ]
        + [
            {
                "element": "direct_labels",
                "fg": spec["fg"],
                "on": spec["on"],
                "role": "text-normal",
            }
            for spec in SERIES
        ]
        + [
            {
                "element": f"label_swatch_{spec['id']}",
                "fg": spec["fg"],
                "on": spec["on"],
                "role": "non-text",
            }
            for spec in SERIES
        ]
        + [
            {
                "element": "tick_labels",
                "fg": "ink",
                "on": "paper",
                "role": "text-normal",
            },
            {
                "element": "axis_titles",
                "fg": "ink",
                "on": "paper",
                "role": "text-normal",
            },
            {
                "element": "stamp_text",
                "fg": "accent-red",
                "on": "paper",
                "role": "text-normal",
            },
            {
                "element": "stamp_border",
                "fg": "accent-red",
                "on": "paper",
                "role": "non-text",
            },
            {
                "element": "gridlines",
                "fg": "rule",
                "min_px": 1,
                "on": "paper",
                "role": "non-text",
            },
            {
                "element": "spines",
                "fg": "rule",
                "min_px": 1,
                "on": "paper",
                "role": "non-text",
            },
        ],
    }

    out_dir = root / "artifacts" / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)
    png_path = out_dir / f"{NAME}.png"
    svg_path = out_dir / f"{NAME}.svg"
    record_path = _records.record_path(root, NAME)

    fig.savefig(png_path, dpi=style.DPI, facecolor=style.token("paper"))

    svg_buf = io.BytesIO()
    fig.savefig(
        svg_buf,
        format="svg",
        metadata={"Date": None},
        facecolor=style.token("paper"),
    )
    svg_path.write_bytes(svg_buf.getvalue())
    _records.write_record(root, record)
    plt.close(fig)
    print(
        f"figures: built {NAME} -> "
        f"{png_path.relative_to(root).as_posix()}, "
        f"{svg_path.relative_to(root).as_posix()}, "
        f"{record_path.relative_to(root).as_posix()} (stamp: {stamp})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(build_figure(Path(__file__).resolve().parents[2]))
