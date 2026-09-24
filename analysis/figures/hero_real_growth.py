"""Hero figure: hero_real_growth_v1 — real 60/40 growth with drawdown bands.

The Pass 1.2 hero exhibit: the canonical monthly-rebalanced REAL 60/40
growth index on an honestly declared log scale, with every qualifying
(>=15%, real) drawdown episode rendered as a HATCH-ONLY data-bad band
behind the unbroken primary solid line (transparent fill, the band's
own stroke set: the locked 4px slash hatch). Data is read straight from
the two registered artifacts — the monthly series CSV (the growth path
is the ``real`` column as-is) and the episodes CSV (the bands) — no .xls,
no metric re-derivation, no hard-coded numbers: bands, the keep-out
episode count, labels, and alt text are all computed from the artifacts.

Layout (1200x800 canvas): the top-left keep-out band holds the computed
episode-count line at the top and the compact four-line release stamp
below it (both inside STAMP_RECT_PX, so gate 7's outside-rect pixel
check stays legible when the count or the BUILD-HEAD leg changes). The
top-right band holds the two swatch-keyed series labels (the growth line's own
solid stroke beside its name; the band's own hatch beside its name; no
leader rules). Each episode carries a direct peak-year label on the
paper above its band's top edge, keyed by a small swatch in the band's
own hatch (beside the label, never inside a band); the labels sit in
the paper strip between the keep-out band and the axes top, in up to
two staggered rows with measured overlap guards. The axes occupy the
lower region, log scale, honest y title.
"""

from __future__ import annotations

import io
import math
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import Rectangle
from matplotlib.ticker import FixedLocator, FuncFormatter
from matplotlib.transforms import Bbox

from analysis.figures import _records, style
from analysis.figures.rebalance_growth import (
    _add_stamp,
    _fmt,
    _humanize_ym,
    _parse_dates,
    _rects_overlap,
    _stamp_lines,
)
from analysis.metrics.drawdown import EPS, THRESHOLD

NAME = "hero_real_growth_v1"
SCRIPT_REL = "analysis/figures/hero_real_growth.py"

#: The two registered inputs: the growth index first, the episodes
#: second (same artifact-reading precedent as the pilot).
SOURCE_ARTIFACTS = (
    "canonical_60_40_monthly_v1",
    "60_40_drawdown_episodes_real_v1",
)

UNITS = "growth index, decimal (base 1.0 at 1871.01)"

SERIES_LINE_ID = "real_growth_line"
BANDS_ID = "drawdown_bands"

#: Declaration order: the line first, the bands second.
SERIES = (
    {
        "dash": "solid",
        "display_name": "Growth of $1 (real)",
        "fg": "ink",
        "id": SERIES_LINE_ID,
        "on": "paper",
        "role": "primary",
    },
    {
        "display_name": "Drawdown episodes \u2265 15%",
        "fg": "data-bad",
        "id": BANDS_ID,
        "on": "paper",
        "role": "band",
    },
)

BAND_UNITS = (
    "drawdown depth, decimal fraction of the peak value "
    "(1 - trough/peak; 0.15 = a 15% drawdown)"
)

X_LABEL = "Year"
Y_LABEL = "Growth of $1, log scale"

#: Locked layout fractions: the axes occupy the LOWER region (top edge
#: at y-down 420px = 0.475 of the 800px canvas), leaving the whole top
#: band: the keep-out block (y-down 24-270, left), the two swatch-keyed
#: series labels (y-down 60/135, right), and the per-episode label
#: strip on paper above the bands' tops (y-down 272-418).
AX_FRACTIONS = {"left": 0.165, "bottom": 0.215, "right": 0.985, "top": 0.475}

X_MIN, X_MAX = 1870.0, 2030.0
#: Log-padding of the data range: 0.15 decades of headroom below the
#: minimum and above the maximum.
Y_LOG_PAD_LO, Y_LOG_PAD_HI = 0.15, 0.15

#: Top-right swatch-keyed series labels: canvas-px anchors (ha=right,
#: va=center). y-down: the growth line at 60, the bands at 135.
GROWTH_LABEL_ANCHOR_PX = (1160.0, 60.0)
BANDS_LABEL_ANCHOR_PX = (1160.0, 135.0)
SWATCH_LEN_PX = 40.0
SWATCH_GAP_PX = 12.0
BAND_SWATCH_PX = (40.0, 14.0)  # the main label's hatched swatch sample

#: Per-episode direct labels: the peak year plus a small swatch in the
#: band's own hatch, on the paper ABOVE the band's top edge (the bands
#: are full axes height, so the paper beside a band is the strip above
#: the axes), staggered in up to two rows (canvas px, y-down) between
#: the keep-out band (bottom 270) and the axes top (420). Two rows are
#: the strip's capacity at the 11pt serif label height (~50px, the gate-4
#: display floor is the 11pt render, so the rows must pitch >= 52px).
EP_LABEL_ROWS_PX = (300.0, 354.0)
EP_SWATCH_PX = (16.0, 10.0)  # the small hatched swatch beside each year
EP_SWATCH_GAP_PX = 6.0

#: The computed episode-count line: canvas-px top-left anchor at the TOP
#: of the keep-out band; the stamped block anchors directly below it, at
#: a runtime-measured offset (the block's 4-line height is the binding
#: constraint: 11pt count ~37px + the 10pt block ~202px must share the
#: band's 246px of height, so the stamp anchor is computed, not guessed).
COUNT_ANCHOR_PX = (48.0, 24.0)
COUNT_STAMP_GAP_PX = 3.0


def _load_inputs(root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The two source artifacts: the monthly series and the episodes CSV.

    The series values are parsed from the raw CSV text with Python
    ``float()`` — the same parse the metrics stage used to derive the
    episodes — so the byte-exact cross-artifact check below compares
    identical doubles (a third-party CSV float parser can differ in the
    last ulp and would false-positive the check).
    """
    series_path = root / "artifacts" / "series" / "canonical_60_40_monthly_v1.csv"
    episodes_path = (
        root / "artifacts" / "metrics" / "60_40_drawdown_episodes_real_v1.csv"
    )
    if not series_path.is_file():
        raise FileNotFoundError(
            f"missing source artifact {series_path.relative_to(root)} "
            "(run the series stage first)"
        )
    if not episodes_path.is_file():
        raise FileNotFoundError(
            f"missing source artifact {episodes_path.relative_to(root)} "
            "(run the metrics stage first)"
        )
    lines = series_path.read_text(encoding="utf-8").split("\n")
    header, *rows = lines
    if header.strip() != "date,real,nominal":
        raise ValueError(f"unexpected series CSV header {header!r}")
    dates: list[str] = []
    real: list[float] = []
    nominal: list[float] = []
    for row in rows:
        if not row:
            continue
        parts = row.split(",")
        if len(parts) != 3:
            raise ValueError(f"malformed series CSV row: {row!r}")
        dates.append(parts[0])
        real.append(float(parts[1]))
        nominal.append(float(parts[2]))
    if not dates:
        raise ValueError("series CSV carries no data rows")
    series = pd.DataFrame({"date": dates, "real": real, "nominal": nominal})
    # All cells as native strings: the recovery cells of an open episode
    # are empty, and the dates must never pass through a float column.
    episodes = pd.read_csv(episodes_path, dtype=str, keep_default_na=False)
    expected = [
        "peak_date",
        "peak_value",
        "trough_date",
        "trough_value",
        "recovery_date",
        "recovery_value",
        "depth",
    ]
    if list(episodes.columns) != expected:
        raise ValueError(f"unexpected episodes CSV columns: {list(episodes.columns)}")
    return series, episodes


def _check_episodes_against_series(
    series: pd.DataFrame, episodes: pd.DataFrame
) -> None:
    """The episodes CSV must re-derive from the series CSV, byte-exact.

    Every date cell must exist on the series index and every value cell
    must equal the series value at that date (the repr() round-trip is
    exact); the depth cell must re-derive as 1 - trough/peak and clear
    the >=15% qualifying threshold; the recovery of an open episode must
    be empty. A mismatch is a cross-artifact state: fail the build
    loudly instead of rendering bands the series does not support.
    """
    dates = {str(d): i for i, d in enumerate(series["date"])}
    values = list(series["real"])
    for pos, row in enumerate(episodes.itertuples(index=False)):
        parsed: dict[str, float] = {}
        for field in ("peak_date", "trough_date"):
            label = str(getattr(row, field))
            if label not in dates:
                raise ValueError(
                    f"episodes row {pos + 1}: {field} {label!r} is not on the "
                    "series date index"
                )
            cell = str(getattr(row, field.replace("_date", "_value")))
            if float(cell) != values[dates[label]]:
                raise ValueError(
                    f"episodes row {pos + 1}: {field} value {cell!r} does not "
                    f"match the series value {values[dates[label]]!r}"
                )
            parsed[field.replace("_date", "_value")] = float(cell)
        # The depth cell must re-derive from the (now-verified) peak and
        # trough — the repr() round-trip is exact, so byte-exact equality
        # holds — and the row must clear the qualifying threshold, else a
        # hand-edited artifact would smuggle in a band the metrics stage
        # never emitted.
        depth_cell = float(str(row.depth))
        expected_depth = 1.0 - parsed["trough_value"] / parsed["peak_value"]
        if depth_cell != expected_depth:
            raise ValueError(
                f"episodes row {pos + 1}: depth {depth_cell!r} does not "
                f"re-derive as 1 - trough/peak ({expected_depth!r})"
            )
        if depth_cell < THRESHOLD - EPS:
            raise ValueError(
                f"episodes row {pos + 1}: depth {depth_cell!r} is below the "
                f"{THRESHOLD:g} qualifying threshold"
            )
        rec_label = str(row.recovery_date)
        if rec_label:
            if rec_label not in dates:
                raise ValueError(
                    f"episodes row {pos + 1}: recovery_date {rec_label!r} is not "
                    "on the series date index"
                )
            if float(str(row.recovery_value)) != values[dates[rec_label]]:
                raise ValueError(
                    f"episodes row {pos + 1}: recovery_value does not match "
                    f"the series value at {rec_label}"
                )
        elif not (row.recovery_date == "" and row.recovery_value == ""):
            raise ValueError(
                f"episodes row {pos + 1}: open episodes leave BOTH recovery cells empty"
            )


def _band_x_extents(
    series: pd.DataFrame, episodes: pd.DataFrame, x: pd.Series
) -> list[tuple[float, float]]:
    """The plot-x span of every episode band (peak to recovery, or the
    series tail for an open episode)."""
    x_by_label = {str(d): float(xv) for d, xv in zip(series["date"], x)}
    tail_x = float(x.iloc[-1])
    extents: list[tuple[float, float]] = []
    for row in episodes.itertuples(index=False):
        x0 = x_by_label[str(row.peak_date)]
        rec = str(row.recovery_date)
        x1 = x_by_label[rec] if rec else tail_x
        if not x0 < x1:
            raise ValueError(
                f"episode band {row.peak_date}: peak x {x0} is not before "
                f"recovery/tail x {x1}"
            )
        extents.append((x0, x1))
    return extents


def _alt_text(
    series: pd.DataFrame,
    episodes: pd.DataFrame,
    x: pd.Series,
    values: pd.Series,
) -> dict:
    """The EXPERIENCE.md v1 alt-text record, computed from the artifacts.

    Carries the full locked field set (incl. pairing_applies) plus the
    PASS-1.2 content: the log declaration, the endpoints, the extremes,
    and what the bands mark.
    """
    start = str(series["date"].iloc[0])
    end = str(series["date"].iloc[-1])
    start_h, end_h = _humanize_ym(start), _humanize_ym(end)
    v_start, v_end = float(values.iloc[0]), float(values.iloc[-1])
    v_np = values.to_numpy()
    i_min = int(v_np.argmin())
    i_max = int(v_np.argmax())
    min_h = _humanize_ym(str(series["date"].iloc[i_min]))
    max_h = _humanize_ym(str(series["date"].iloc[i_max]))
    terminal_clause = ", the terminal value" if i_max == len(values) - 1 else ""
    n = len(episodes)
    trend = (
        f"Real 60/40 (monthly-rebalanced) grows from {_fmt(v_start)} at "
        f"{start_h} to {_fmt(v_end)} at {end_h}, plotted on a log scale: "
        "equal slopes are equal growth rates."
    )
    extremes = (
        f"Extremes: the minimum is {_fmt(float(values.iloc[i_min]))} at {min_h}; "
        f"the maximum is {_fmt(float(values.iloc[i_max]))} at {max_h}{terminal_clause}."
    )
    bands_sentence = (
        f"{n} hatched bands mark the drawdown episodes of 15% or worse in real "
        "terms (peak-to-new-high stretches; the count is computed from the "
        "episodes artifact and stated in the keep-out band): hatch-only "
        "data-bad strokes, transparent fill. "
    )
    alt_text = (
        f"Line chart of the real 60/40 growth index (monthly-rebalanced), "
        f"{start_h} to {end_h}. "
        f"Axes: {X_LABEL}, {Y_LABEL}. {trend} {extremes} "
        f"{bands_sentence}"
        "2 series: the real growth line (primary, solid) and the drawdown "
        "bands (band, hatched)."
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
                "display_name": SERIES[0]["display_name"],
                "id": SERIES_LINE_ID,
                "role": "primary",
                "units": UNITS,
            },
            {
                "display_name": SERIES[1]["display_name"],
                "id": BANDS_ID,
                "role": "band",
                "units": BAND_UNITS,
            },
        ],
        "trend": trend,
    }


def _count_line_text(n: int) -> str:
    """The keep-out episode-count line: computed, never hand-typed.

    Bounded to the keep-out band's width at the mono-stamp class font:
    the name of the phenomenon lives in the bands' series label and the
    caption below the chart.
    """
    return f"{n} EPISODES >= 15%"


def _hatch_line(
    fig: plt.Figure,
    rect_px: tuple[float, float, float, float],
    *,
    gid: str | None = None,
) -> plt.Line2D:
    """The band's stroke set inside a display-px box, as one line artist.

    ``rect_px`` is ``(x0, y0, x1, y1)`` in canvas px with y UP (the
    canvas origin is bottom-left). Disjoint segments are separated by
    None breaks so one Line2D rasterizes the whole hatch; the stroke is
    the locked ``BAND_HATCH_LINWIDTH_PX`` (canvas px -> pt at the
    locked DPI). Drawn at zorder 1.5: over the transparent band patch
    (1.0), under the primary line (2.0).
    """
    w_px, h_px = style.CANVAS_PX
    pts: list[tuple[float, float] | None] = []
    for a, b in style.band_hatch_segments(rect_px):
        pts.extend([a, b, None])
    # None entries are matplotlib segment breaks; the stubs don't model
    # them, so the data arrays are cast to their runtime contract.
    xs = [None if p is None else p[0] / w_px for p in pts]
    ys = [None if p is None else p[1] / h_px for p in pts]
    line = plt.Line2D(
        cast("list[float]", xs),
        cast("list[float]", ys),
        transform=fig.transFigure,
        color=style.token("data-bad"),
        linestyle="-",
        linewidth=style.BAND_HATCH_LINWIDTH_PX * 72.0 / style.DPI,
        solid_capstyle="butt",
        zorder=1.5,
    )
    if gid is not None:
        line.set_gid(gid)
    fig.add_artist(line)
    return line


def build_figure(root: Path) -> int:
    """Build, export, and record the hero figure under ``root``.

    Writes ``artifacts/figures/hero_real_growth_v1.{png,svg}`` and its
    ``.figure.json`` record; returns 0 on success. Layout violations
    (the keep-out and overlap guards) raise AssertionError instead of
    returning a non-zero exit code.
    """
    style.apply_style()
    # D3 floor, asserted before export: the band hatch is a RENDER-px
    # contract (>=4px stroke, >=8px pitch at the 1200px render).
    if style.BAND_HATCH_LINWIDTH_PX < 4.0:
        raise AssertionError(
            f"band hatch linewidth {style.BAND_HATCH_LINWIDTH_PX}px is below "
            "the 4px render floor"
        )
    if style.BAND_HATCH_PITCH_PX < style.HATCH_MIN_PITCH_PX:
        raise AssertionError(
            f"band hatch pitch {style.BAND_HATCH_PITCH_PX}px is below the "
            f"{style.HATCH_MIN_PITCH_PX}px render floor"
        )

    series, episodes = _load_inputs(root)
    _check_episodes_against_series(series, episodes)
    # Decimal plot-x: the pilot's DATA.md-safe parse of the YYYY.MM cells.
    x = _parse_dates(series["date"].astype(float))
    values = series["real"]
    # The x range is locked (X_MIN/X_MAX); a vintage whose series extends
    # past it would be silently clipped by set_xlim, so guard it loudly,
    # like the builder's other layout invariants.
    x_lo, x_hi = float(x.min()), float(x.max())
    if not (X_MIN <= x_lo and x_hi <= X_MAX):
        raise AssertionError(
            f"series x-span [{x_lo}, {x_hi}] does not fit the locked range "
            f"[{X_MIN}, {X_MAX}]; set_xlim would clip the data"
        )
    band_x = _band_x_extents(series, episodes, x)
    if len(band_x) != len(episodes):
        raise AssertionError("band extents disagree with the episodes artifact")

    v_min, v_max = float(values.min()), float(values.max())
    y_lo = 10.0 ** (math.log10(v_min) - Y_LOG_PAD_LO)
    y_hi = 10.0 ** (math.log10(v_max) + Y_LOG_PAD_HI)

    fig, ax = plt.subplots(figsize=style.FIGSIZE_IN, facecolor=style.token("paper"))
    fig.subplots_adjust(**AX_FRACTIONS)
    ax.set_facecolor(style.token("paper"))
    ax.grid(axis="y", color=style.token("rule"), linewidth=0.5)

    # The unbroken primary solid line (the ladder's primary weight).
    dash, lw_pt = style.dash_style("solid")
    line = ax.plot(
        x,
        values,
        color=style.token("ink"),
        linestyle=dash,
        linewidth=lw_pt,
        label=SERIES[0]["display_name"],
        solid_capstyle="butt",
        dash_capstyle="butt",
    )[0]

    ax.set_yscale("log")
    ax.set_xlim(X_MIN, X_MAX)
    ax.set_ylim(y_lo, y_hi)
    # Honest decades: on the short axes a LogLocator thins its ticks to
    # every third decade, so the decade set is pinned explicitly to the
    # powers of ten inside the data-driven limits (deterministic per
    # vintage, no auto-thinning).
    decades = [
        10.0**k
        for k in range(math.floor(math.log10(y_lo)), math.ceil(math.log10(y_hi)) + 1)
        if y_lo <= 10.0**k <= y_hi
    ]
    if len(decades) < 2:
        raise AssertionError(f"not enough decade ticks for the y range: {decades}")
    ax.yaxis.set_major_locator(FixedLocator(decades))
    ax.yaxis.set_major_formatter(
        FuncFormatter(lambda v, _: f"{float(v):,.0f}".replace(",", ""))
    )
    ax.minorticks_off()
    ax.set_xticks(range(1880, 2030, 20))
    ax.set_xlabel(X_LABEL, size=13.0)
    ax.set_ylabel(Y_LABEL, size=13.0)
    ax.tick_params(axis="both", which="major", labelsize=13.0)
    for spine in ax.spines.values():
        spine.set_edgecolor(style.token("rule"))
        spine.set_linewidth(0.75)
    for spine_name in ("top", "right"):
        ax.spines[spine_name].set_visible(False)

    # Hatch-only drawdown bands: a transparent patch plus the band's own
    # stroke set (the locked 4px slash hatch in data-bad, explicit
    # lines — matplotlib's hatch strings cannot carry the stroke and
    # pitch), both behind the line. Drawn after the axes config so the
    # band's display-px extents come from the final data transforms.
    _w_px, _h_px = style.CANVAS_PX
    for i, (x0, x1) in enumerate(band_x):
        patch = Rectangle(
            (x0, y_lo),
            width=x1 - x0,
            height=y_hi - y_lo,
            transform=ax.transData,
            facecolor=(1.0, 1.0, 1.0, 0.0),  # transparent: hatch only
            edgecolor="none",
            zorder=1.0,
            gid=f"drawdown-band-{i:02d}",
        )
        ax.add_patch(patch)
        band_px0 = float(ax.transData.transform((x0, y_lo))[0])
        band_px1 = float(ax.transData.transform((x1, y_lo))[0])
        _hatch_line(
            fig,
            (
                band_px0,
                AX_FRACTIONS["bottom"] * _h_px,
                band_px1,
                AX_FRACTIONS["top"] * _h_px,
            ),
            gid=f"drawdown-band-hatch-{i:02d}",
        )

    w_px, h_px = style.CANVAS_PX
    axis_top_display = h_px - AX_FRACTIONS["top"] * h_px  # y-down px of the axes top
    renderer = fig.canvas.get_renderer()  # type: ignore[attr-defined]

    # --- Top-right: the two swatch-keyed series labels -------------------
    growth_label = fig.text(
        GROWTH_LABEL_ANCHOR_PX[0] / w_px,
        1.0 - GROWTH_LABEL_ANCHOR_PX[1] / h_px,
        SERIES[0]["display_name"],
        family=style.SERIF_FAMILY,
        size=11.0,
        color=style.token("ink"),
        ha="right",
        va="center",
    )
    bands_label = fig.text(
        BANDS_LABEL_ANCHOR_PX[0] / w_px,
        1.0 - BANDS_LABEL_ANCHOR_PX[1] / h_px,
        SERIES[1]["display_name"],
        family=style.SERIF_FAMILY,
        size=11.0,
        color=style.token("ink"),
        ha="right",
        va="center",
    )
    # The growth swatch: a short sample of the line's own stroke.
    ext = growth_label.get_window_extent(renderer)
    swatch_right_px = float(ext.x0) - SWATCH_GAP_PX
    swatch_cy_px = (float(ext.y0) + float(ext.y1)) / 2.0
    growth_swatch = plt.Line2D(
        [(swatch_right_px - SWATCH_LEN_PX) / w_px, swatch_right_px / w_px],
        [swatch_cy_px / h_px, swatch_cy_px / h_px],
        transform=fig.transFigure,
        color=style.token("ink"),
        linestyle=dash,
        linewidth=lw_pt,
        solid_capstyle="butt",
        dash_capstyle="butt",
    )
    fig.add_artist(growth_swatch)
    # The bands swatch: a short sample in the band's own stroke set
    # (the locked hatch, data-bad, transparent fill).
    ext = bands_label.get_window_extent(renderer)
    bw, bh = BAND_SWATCH_PX
    bs_right_px = float(ext.x0) - SWATCH_GAP_PX
    bs_cy = (float(ext.y0) + float(ext.y1)) / 2.0
    bands_swatch = _hatch_line(
        fig,
        (bs_right_px - bw, bs_cy - bh / 2.0, bs_right_px, bs_cy + bh / 2.0),
        gid="drawdown-bands-swatch",
    )

    # --- Per-episode direct labels: the peak year on paper above the band.
    # Greedy staggered rows, in peak-x order; every placement is checked
    # against the already-placed labels (text + swatch) with a 2px gap.
    year_labels: list[plt.Text] = []
    year_swatches: list[Rectangle | plt.Line2D] = []
    placed_rects: list[Bbox] = []
    for i, row in enumerate(episodes.itertuples(index=False)):
        cx_data = (band_x[i][0] + band_x[i][1]) / 2.0
        cx_px = float(ax.transData.transform((cx_data, y_lo))[0])
        label = fig.text(
            cx_px / w_px,
            0.0,  # row chosen below
            str(row.peak_date)[:4],
            family=style.SERIF_FAMILY,
            size=11.0,
            color=style.token("ink"),
            ha="center",
            va="center",
        )
        sw_w, sw_h = EP_SWATCH_PX
        gap = EP_SWATCH_GAP_PX
        row_px = None
        for candidate in EP_LABEL_ROWS_PX:
            # The ink box of ha="center" is not centered on the advance
            # center, so the swatch slot is measured from the placed
            # label's real extent on each candidate row, never assumed.
            label.set_position((cx_px / w_px, 1.0 - candidate / h_px))
            ext = label.get_window_extent(renderer)
            left = float(ext.x0) - gap - sw_w
            top = candidate - float(ext.height) / 2.0
            bottom = candidate + float(ext.height) / 2.0
            cand_rect = Bbox.from_bounds(
                left, top, sw_w + gap + float(ext.width), float(ext.height)
            )
            if any(_rects_overlap(cand_rect, r) for r in placed_rects):
                continue
            if top < style.STAMP_RECT_PX[3] + 2.0 or bottom > axis_top_display - 2.0:
                continue
            if left < 0.0 or float(ext.x1) > w_px:
                continue
            row_px = candidate
            break
        if row_px is None:
            raise AssertionError(
                f"no label row clears the guards for episode "
                f"{row.peak_date} (band x {cx_px:.0f}px)"
            )
        # The label is already on its row; lock the final extents and put
        # the swatch directly beside the measured ink box.
        final_ext = label.get_window_extent(renderer)
        cy_px = row_px
        swatch = _hatch_line(
            fig,
            (
                float(final_ext.x0) - gap - sw_w,
                h_px - (cy_px + sw_h / 2.0),
                float(final_ext.x0) - gap,
                h_px - (cy_px - sw_h / 2.0),
            ),
            gid=f"drawdown-band-swatch-{i:02d}",
        )
        placed_rects.append(
            Bbox.from_bounds(
                float(final_ext.x0) - gap - sw_w,
                cy_px - float(final_ext.height) / 2.0,
                sw_w + gap + float(final_ext.width),
                float(final_ext.height),
            )
        )
        year_labels.append(label)
        year_swatches.append(swatch)

    # --- The computed episode-count line, at the top of the keep-out band.
    # The stamped block anchors below it at a measured offset.
    count_text = fig.text(
        COUNT_ANCHOR_PX[0] / w_px,
        1.0 - COUNT_ANCHOR_PX[1] / h_px,
        _count_line_text(len(episodes)),
        family=style.MONO_FAMILY_LIST,
        size=11.0,
        color=style.token("accent-red"),
        ha="left",
        va="top",
        gid="episode-count",
    )
    count_extent = count_text.get_window_extent(renderer)
    count_height_px = float(count_extent.y1) - float(count_extent.y0)
    # The stamped frame pads pad_y above its text anchor, so the anchor
    # carries the pad plus the nominal gap (the -2deg swing eats ~0.6 of
    # the measured gap; the guard below asserts the realized clearance).
    hero_stamp_anchor_y = (
        COUNT_ANCHOR_PX[1]
        + count_height_px
        + 2.0 * style.STAMP_PAD_Y_PX
        + COUNT_STAMP_GAP_PX
    )

    # --- The release stamp (the same four-line corner block as the
    # pilot, re-anchored under the count line). ----
    stamp = _records.stamp_string(
        _records.resolve_vintage(root),
        _records.resolve_build_head(root),
        SCRIPT_REL,
    )
    stamp_text, stamp_frame = _add_stamp(
        fig, stamp, SCRIPT_REL, anchor_px=(COUNT_ANCHOR_PX[0], hero_stamp_anchor_y)
    )

    # One forced draw lays out every real artist (ticks included); the
    # recorded measurements are then the real renderer extents.
    renderer = fig.canvas.get_renderer()  # type: ignore[attr-defined]
    fig.draw(renderer)

    # --- Layout guards, all from measured extents. -------------------------
    sx0, sy0, sx1, sy1 = style.STAMP_RECT_PX
    # Extents are y-up display px (origin bottom-left); STAMP_RECT_PX is
    # y-down from the top — the keep-out band in y-up display px is:
    keepout_up = (sx0, h_px - sy1, sx1, h_px - sy0)  # (x0, y0, x1, y1)
    renderer = fig.canvas.get_renderer()  # type: ignore[attr-defined]
    fig.canvas.draw()  # resolves the axes-label offsets before measuring

    def _inside_keep_out(ext, who: str) -> None:
        if (
            float(ext.x0) < keepout_up[0]
            or float(ext.y0) < keepout_up[1]
            or float(ext.x1) > keepout_up[2]
            or float(ext.y1) > keepout_up[3]
        ):
            raise AssertionError(
                f"{who} escapes the keep-out band {style.STAMP_RECT_PX}: "
                f"({float(ext.x0):.1f}, {float(ext.y0):.1f}, {float(ext.x1):.1f}, "
                f"{float(ext.y1):.1f})"
            )

    count_ext = count_text.get_window_extent(renderer)
    _inside_keep_out(count_ext, "episode-count line")
    # The stamped block sits below the count line with the pinned gap;
    # the frame's worst corner (the -2deg swing) bounds the block.
    frame_corners = cast(
        "Sequence[tuple[float, float]]", stamp_frame.get_path().vertices
    )  # figure fractions
    frame_top_ydown = min(
        h_px - (float(v[1]) * h_px)
        for v in frame_corners  # fraction -> y-up px
    )
    count_bottom_ydown = h_px - float(count_ext.y0)
    # 3.0px realized clearance: the nominal gap minus the pad/rotation
    # swing that the anchor formula already accounts for.
    if frame_top_ydown < count_bottom_ydown + COUNT_STAMP_GAP_PX - 1.0:
        raise AssertionError(
            "episode-count line overlaps the stamped block "
            f"(count bottom {count_bottom_ydown:.1f}px, frame top "
            f"{frame_top_ydown:.1f}px y-down, gap "
            f"{COUNT_STAMP_GAP_PX}px)"
        )

    all_label_exts = [
        growth_label.get_window_extent(renderer),
        bands_label.get_window_extent(renderer),
    ] + [lab.get_window_extent(renderer) for lab in year_labels]
    for who, ext in zip(
        ["growth", "bands"]
        + [f"episode {row.peak_date}" for row in episodes.itertuples(index=False)],
        all_label_exts,
    ):
        if (
            float(ext.x0) < 0.0
            or float(ext.y0) < 0.0
            or float(ext.x1) > w_px
            or float(ext.y1) > h_px
        ):
            raise AssertionError(f"label {who!r} escapes the canvas")
        if (
            float(ext.x0) < sx1 + 2.0
            and float(ext.x1) > sx0 - 2.0
            and float(ext.y1) > keepout_up[1] - 2.0
            and float(ext.y0) < keepout_up[3] + 2.0
        ):
            raise AssertionError(f"label {who!r} intrudes on the keep-out band")
        if float(ext.y0) < h_px - axis_top_display - 2.0:
            raise AssertionError(f"label {who!r} sinks below the axes top")
    # No two labels overlap; no swatch crosses another label.
    for i in range(len(all_label_exts)):
        for j in range(i + 1, len(all_label_exts)):
            if _rects_overlap(all_label_exts[i], all_label_exts[j]):
                raise AssertionError(f"labels {i} and {j} overlap")
    swatch_exts = [
        growth_swatch.get_window_extent(renderer),
        bands_swatch.get_window_extent(renderer),
    ] + [sw.get_window_extent(renderer) for sw in year_swatches]
    for sw_ext in swatch_exts:
        if (
            float(sw_ext.x0) < 0.0
            or float(sw_ext.y0) < 0.0
            or float(sw_ext.x1) > w_px
            or float(sw_ext.y1) > h_px
        ):
            raise AssertionError("a swatch escapes the canvas")
        for who, ext in zip(
            ["growth", "bands"]
            + [f"episode {row.peak_date}" for row in episodes.itertuples(index=False)],
            all_label_exts,
        ):
            if _rects_overlap(sw_ext, ext):
                raise AssertionError(f"a swatch crosses label {who!r}")
    # The growth swatch must clear the keep-out band horizontally (it
    # sits in the top-right band, like the pilot's swatches).
    if float(growth_swatch.get_window_extent(renderer).x0) < sx1 + 5:
        raise AssertionError("the growth swatch intrudes on the stamp band")
    ylabel_ext = ax.yaxis.get_label().get_window_extent(renderer)
    xlabel_ext = ax.xaxis.get_label().get_window_extent(renderer)
    for name, ext in (("y title", ylabel_ext), ("x title", xlabel_ext)):
        if (
            float(ext.x0) < 0.0
            or float(ext.y0) < 0.0
            or float(ext.x1) > w_px
            or float(ext.y1) > h_px
        ):
            raise AssertionError(f"{name} escapes the canvas")
    # The y title (rotated, left of the axes) must clear the keep-out
    # block: its top may not rise into the block's x band.
    if (
        float(ylabel_ext.y1) > keepout_up[1] - 8.0
        and float(ylabel_ext.x1) > sx0
        and float(ylabel_ext.x0) < sx1
    ):
        raise AssertionError("y title collides with the keep-out block")
    # The growth line must stay out of the episode-label strip: the strip
    # above the axes top is paper only while the highest point of the
    # line clears it; a future vintage that pushes the line into the
    # strip fails the build instead of letting a label land on the line.
    i_max = int(values.to_numpy().argmax())
    hi_yup = float(
        ax.transData.transform((float(x.iloc[i_max]), float(values.iloc[i_max])))[1]
    )
    if h_px - hi_yup < axis_top_display + 6.0:
        raise AssertionError(
            "the growth line rises into the episode-label strip "
            f"(top point {h_px - hi_yup:.1f}px y-down, strip floor "
            f"{axis_top_display + 6.0:.1f}px y-down)"
        )

    # --- Measurements -------------------------------------------------------
    tick_probe = ax.get_xticklabels()[1]
    tick_px = style.measure_text_px(tick_probe)
    title_px = max(
        style.measure_text_glyph_px(ax.xaxis.get_label()),
        style.measure_text_glyph_px(ax.yaxis.get_label()),
    )
    growth_label_px = style.measure_text_px(growth_label)
    bands_label_px = style.measure_text_px(bands_label)
    year_label_px = [style.measure_text_px(lab) for lab in year_labels]
    line_px = style.measure_line_px(line)
    stamp_px = style.measure_text_px(stamp_text) / len(_stamp_lines(stamp, SCRIPT_REL))
    count_px = style.measure_text_px(count_text)
    hatch_px = style.BAND_HATCH_LINWIDTH_PX
    scale = style.CANVAS_TO_DISPLAY

    def m(cls: str, element: str, render_px: float) -> dict:
        return {
            "class": cls,
            "element": element,
            "render_px": render_px,
            "display_px": render_px * scale,
        }

    measurements: list[dict] = [
        m("series-line", f"series_line_{SERIES_LINE_ID}", line_px),
        # The band hatch: a floor-free class (its >=4px is a RENDER-px
        # contract riding the min_px style declaration below, not a
        # 375px display floor); the recorded rescale is traceability.
        m("band-hatch", "band_hatch", hatch_px),
        m("series-label", f"direct_label_{SERIES_LINE_ID}", growth_label_px),
        m("series-label", f"direct_label_{BANDS_ID}", bands_label_px),
    ]
    measurements += [
        m("series-label", f"band_year_label_{i:02d}", px)
        for i, px in enumerate(year_label_px)
    ]
    measurements += [
        m("series-line", f"label_swatch_{SERIES_LINE_ID}", line_px),
        m("band-hatch", f"label_swatch_{BANDS_ID}", hatch_px),
    ]
    measurements += [
        m("band-hatch", f"band_year_swatch_{i:02d}", hatch_px)
        for i in range(len(year_swatches))
    ]
    measurements += [
        m("caption-class", "tick_labels", tick_px),
        m("caption-class", "axis_titles", title_px),
        m("mono-stamp", "stamp_text", stamp_px),
        m("mono-stamp", "count_line", count_px),
        m("hairline", "gridlines", style.canvas_px_of_pt(0.5)),
        m("hairline", "spines", style.canvas_px_of_pt(0.75)),
        m("hairline", "stamp_border", style.STAMP_BORDER_PX),
    ]

    record = {
        "alt_text": _alt_text(series, episodes, x, values),
        "builder": SCRIPT_REL,
        "canvas_px": {"height": style.CANVAS_PX[1], "width": style.CANVAS_PX[0]},
        "measurements": measurements,
        "name": NAME,
        "series": [
            {
                "dash": "solid",
                "display_name": SERIES[0]["display_name"],
                "fg": "ink",
                "id": SERIES_LINE_ID,
                "on": "paper",
                "role": "primary",
                "units": UNITS,
            },
            {
                "display_name": SERIES[1]["display_name"],
                "fg": "data-bad",
                "id": BANDS_ID,
                "on": "paper",
                "role": "band",
                "units": BAND_UNITS,
            },
        ],
        "source_artifacts": list(SOURCE_ARTIFACTS),
        "stamp": stamp,
        "style_declarations": [
            {
                "element": "series_line",
                "fg": "ink",
                "on": "paper",
                "role": "data-series",
            },
            {
                "element": "band_hatch",
                "fg": "data-bad",
                "on": "paper",
                "role": "non-text",
                "min_px": 4,
            },
            {
                "element": "direct_labels",
                "fg": "ink",
                "on": "paper",
                "role": "text-normal",
            },
            {
                "element": "band_year_labels",
                "fg": "ink",
                "on": "paper",
                "role": "text-normal",
            },
            {
                "element": f"label_swatch_{SERIES_LINE_ID}",
                "fg": "ink",
                "on": "paper",
                "role": "non-text",
            },
            {
                "element": f"label_swatch_{BANDS_ID}",
                "fg": "data-bad",
                "on": "paper",
                "role": "non-text",
            },
            {
                "element": "band_year_swatches",
                "fg": "data-bad",
                "on": "paper",
                "role": "non-text",
            },
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
                "element": "count_line",
                "fg": "accent-red",
                "on": "paper",
                "role": "text-normal",
            },
            {
                "element": "gridlines",
                "fg": "rule",
                "on": "paper",
                "role": "non-text",
                "min_px": 1,
            },
            {
                "element": "spines",
                "fg": "rule",
                "on": "paper",
                "role": "non-text",
                "min_px": 1,
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
        f"{record_path.relative_to(root).as_posix()} "
        f"({len(episodes)} band(s), stamp: {stamp})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(build_figure(Path(__file__).resolve().parents[2]))
