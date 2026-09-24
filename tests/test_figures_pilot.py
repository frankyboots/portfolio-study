"""Pilot figure tests (story 1.6): the rebalance_growth construction.

Proves the pilot's accuracy and export discipline: the record schema
(is the EXPERIENCE.md alt-text v1 key set, is the pinned top-level
shape), the stamp format against the AD-6 schema, the export bytes
(canvas size, no wall-clock metadata, stable serialization), and that
the alt text is generated from — not pasted beside — the source
artifacts. One deliberately-wrong variant fails per construction
convention (tampered input data, malformed stamps).
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from analysis.figures import (
    _records,
    rebalance_growth,
)

FIGURE_NAME = "rebalance_growth_v1"


def _staged_copy_ignore(dirpath: str, dirnames: list[str]) -> list[str]:
    """Staged-copy filter: drop pycache and ONLY the exports dir.

    ``artifacts/figures`` (the generated exports) is excluded so the
    build regenerates them; ``analysis/figures`` (the builder code)
    stays in the staged tree — a blanket ``"figures"`` pattern would
    wrongly drop the code directory too. (The returned names are the
    ones copytree skips.)
    """
    ignored = [d for d in dirnames if d == "__pycache__"]
    if Path(dirpath).name == "artifacts" and "figures" in dirnames:
        ignored.append("figures")
    return ignored


def _stage_repo(staged: Path) -> None:
    for name in ("analysis", "config", "artifacts"):
        shutil.copytree(
            REPO_ROOT / name,
            staged / name,
            ignore=_staged_copy_ignore,
        )
    # Matplotlib font-cache files are build noise, not tree content.
    for stray in staged.glob("**/fontlist*.json"):
        stray.unlink()


ALT_TEXT_KEYS = {
    "alt_text",
    "axis",
    "chart_type",
    "extremes",
    "pairing_applies",
    "range",
    "series",
    "trend",
}
OPTIONAL_ALT_TEXT_KEYS = {"long_description_ref"}
SERIES_ROLES = {"primary", "baseline", "band", "annotation"}
CHART_TYPES = {"line", "bar", "area", "band", "scatter"}
SCALE_VALUES = {"linear", "log"}
MEASUREMENT_CLASSES = {"caption-class", "series-label", "series-line", "mono-stamp"}


@pytest.fixture(scope="module")
def built_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A .git-less repo-shaped root with the pilot figure built in-process."""
    staged = tmp_path_factory.mktemp("pilot") / "repo"
    _stage_repo(staged)
    rc = rebalance_growth.build_figure(staged)
    assert rc == 0, f"pilot build failed on a clean staged root (exit {rc})"
    return staged


def _record(root: Path) -> dict:
    return json.loads(
        _records.record_path(root, FIGURE_NAME).read_text(encoding="utf-8")
    )


# ---------------------------------------------------------------- schema


def test_record_top_level_schema(built_root: Path) -> None:
    rec = _record(built_root)
    assert set(rec) == {
        "name",
        "source_artifacts",
        "canvas_px",
        "series",
        "alt_text",
        "style_declarations",
        "measurements",
        "stamp",
        "builder",
    }
    assert rec["name"] == FIGURE_NAME
    assert rec["builder"] == rebalance_growth.SCRIPT_REL
    assert rec["canvas_px"] == {"width": 1200, "height": 800}
    assert rec["source_artifacts"] == [
        "canonical_60_40_monthly_v1",
        "canonical_60_40_annual_v1",
    ]
    for series in rec["series"]:
        assert set(series) == {
            "id",
            "display_name",
            "role",
            "units",
            "fg",
            "on",
            "dash",
        }
        assert series["role"] in {"primary", "baseline"}
        assert series["dash"] in {"solid", "dashed", "dash-dot", "dotted"}
        for field in ("id", "display_name", "units"):
            assert isinstance(series[field], str) and series[field]
    assert {s["dash"] for s in rec["series"]} == {"solid", "dashed"}
    # The frozen decision: monthly is the primary (solid, data-good),
    # annual the baseline (dashed, data-neutral); primary declared first.
    assert rec["series"][0]["role"] == "primary"
    by_id = {s["id"]: s for s in rec["series"]}
    assert by_id["monthly_rebalanced_real"]["role"] == "primary"
    assert by_id["monthly_rebalanced_real"]["dash"] == "solid"
    assert by_id["monthly_rebalanced_real"]["fg"] == "data-good"
    assert by_id["annual_rebalanced_real"]["role"] == "baseline"
    assert by_id["annual_rebalanced_real"]["dash"] == "dashed"
    assert by_id["annual_rebalanced_real"]["fg"] == "data-neutral"
    for decl in rec["style_declarations"]:
        assert set(decl) in (
            {"element", "fg", "on", "role"},
            {"element", "fg", "on", "role", "min_px"},
        )
        assert decl["role"] in {
            "data-series",
            "non-text",
            "text-normal",
            "text-large",
            "decorative",
        }
    for measurement in rec["measurements"]:
        assert set(measurement) == {"element", "class", "render_px", "display_px"}
    # Every gate-4-checked class is measured, not just some.
    classes = {m["class"] for m in rec["measurements"]}
    assert MEASUREMENT_CLASSES <= classes
    # The leader rules are out, the swatch-keyed labels are in — each swatch is recorded at the
    # series-line level with a non-text declaration (a schema pin, not
    # a pixel-value pin).
    measurement_elements = {m["element"] for m in rec["measurements"]}
    declaration_elements = {d["element"] for d in rec["style_declarations"]}
    for sid in ("monthly_rebalanced_real", "annual_rebalanced_real"):
        assert f"leader_{sid}" not in measurement_elements
        assert f"leader_{sid}" not in declaration_elements
        swatch = next(
            m for m in rec["measurements"] if m["element"] == f"label_swatch_{sid}"
        )
        assert swatch["class"] == "series-line"
        decl = next(
            d
            for d in rec["style_declarations"]
            if d["element"] == f"label_swatch_{sid}"
        )
        assert decl["role"] == "non-text"


def test_alt_text_is_the_v1_key_set(built_root: Path) -> None:
    alt = _record(built_root)["alt_text"]
    assert ALT_TEXT_KEYS <= set(alt)
    assert set(alt) <= ALT_TEXT_KEYS | OPTIONAL_ALT_TEXT_KEYS
    assert isinstance(alt["alt_text"], str) and len(alt["alt_text"]) > 40
    assert alt["chart_type"] in CHART_TYPES
    assert alt["pairing_applies"] in (True, False)
    axis = alt["axis"]
    assert set(axis) == {"x_label", "y_label", "scale"}
    assert axis["scale"] in SCALE_VALUES
    assert axis["x_label"] and axis["y_label"]
    rng = alt["range"]
    assert set(rng) == {"start", "end", "period"}
    assert rng["start"] and rng["end"] and rng["period"]
    assert alt["extremes"] and alt["trend"]
    assert len(alt["series"]) == 2
    for entry in alt["series"]:
        assert set(entry) == {"id", "display_name", "role", "units"}
        assert entry["role"] in SERIES_ROLES
    ids = {entry["id"] for entry in alt["series"]}
    assert ids == {s["id"] for s in _record(built_root)["series"]}
    # The alt-text series sentence names the roles per the frozen decision.
    assert "monthly-rebalanced (primary, solid)" in alt["alt_text"]
    assert "annual-rebalanced (baseline, dashed)" in alt["alt_text"]


def test_stamp_is_the_ad6_schema(built_root: Path) -> None:
    stamp = _record(built_root)["stamp"]
    parsed = _records.parse_stamp(stamp)
    assert parsed is not None
    assert parsed["script"] == rebalance_growth.SCRIPT_REL
    assert parsed["vintage"] == _records.resolve_vintage(built_root)
    assert re.fullmatch(r"[0-9a-f]{7,40}|nogit", parsed["build_head"])


# ---------------------------------------------------------------- bytes


def test_export_bytes_discipline(built_root: Path) -> None:
    figs = _records.record_path(built_root, FIGURE_NAME).parent
    png = (figs / f"{FIGURE_NAME}.png").read_bytes()
    svg_text = (figs / f"{FIGURE_NAME}.svg").read_text(encoding="utf-8")
    record_bytes = _records.record_path(built_root, FIGURE_NAME).read_bytes()

    import struct

    # PNG: valid signature, 1200x800 canvas at the locked size.
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", png[16:24])
    assert (width, height) == (1200, 800)

    # SVG: path-only text, no wall-clock metadata, a stamped group present.
    assert "<?xml" in svg_text[:200]
    assert "dc:date" not in svg_text
    assert '<g id="release-stamp' in svg_text

    # Record: stable serialization, no wall-clock fields anywhere.
    doc = json.loads(record_bytes)
    assert record_bytes.decode("utf-8") == _records.serialize_record(doc), (
        "record file is not canonically serialized"
    )
    flat = json.dumps(doc)
    for wallclock in ("generated_at", "created", "updated", "timestamp", "datetime"):
        assert wallclock not in flat, f"wall-clock field {wallclock!r} in the record"


def test_svg_stripped_stamp_is_byte_stable_across_heads(built_root: Path) -> None:
    """Two builds at different BUILD-HEAD legs strip to identical SVG bytes."""
    from analysis.figures._diff import strip_stamp_groups

    figs = _records.record_path(built_root, FIGURE_NAME).parent
    # This build ran .git-less with no manifest: stamped with the nogit sentinel.
    svg_built = (figs / f"{FIGURE_NAME}.svg").read_text(encoding="utf-8")
    assert "BUILD-HEAD nogit" in svg_built
    # The repo's committed export carries a real short SHA in the same leg;
    # identical content, different head -> the stripped bytes must agree.
    svg_committed = (
        REPO_ROOT / "artifacts" / "figures" / f"{FIGURE_NAME}.svg"
    ).read_text(encoding="utf-8")
    assert svg_built != svg_committed, (
        "premise: the two exports must differ only in the stamp"
    )
    assert strip_stamp_groups(svg_built) == strip_stamp_groups(svg_committed)


# ---------------------------------------------------------------- data fidelity


def test_alt_text_is_generated_from_the_artifacts(built_root: Path) -> None:
    """The alt text reports the source artifacts' terminal values, not prose drift."""
    alt = _record(built_root)["alt_text"]
    annual = built_root / "artifacts" / "series" / "canonical_60_40_annual_v1.csv"
    import csv

    with open(annual, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    last_real = float(rows[-1]["real"])
    last_date = rows[-1]["date"]
    # The terminal date and a comma-grouped reading of the terminal real value
    # must appear in the alt text (the pilot's construction convention).
    assert alt["range"]["end"] == last_date
    assert alt["range"]["start"] == rows[0]["date"]
    terminal = f"{last_real:,.0f}"
    assert terminal in alt["alt_text"], (
        f"terminal real value {terminal} not reported in alt text"
    )
    assert terminal in alt["trend"]


def test_tampered_input_changes_the_record(built_root: Path) -> None:
    """Deliberately-wrong variant: a tampered source CSV must change the record."""
    import tempfile

    rec_before = _record(built_root)
    with tempfile.TemporaryDirectory() as tmp:
        staged = Path(tmp) / "repo"
        _stage_repo(staged)
        # Tamper: double the annual terminal real value (the real column is 2nd).
        annual = staged / "artifacts" / "series" / "canonical_60_40_annual_v1.csv"
        lines = annual.read_text(encoding="utf-8").splitlines()
        date_part, real_part, nominal_part = lines[-1].split(",")
        lines[-1] = f"{date_part},{float(real_part) * 2.0:.2f},{nominal_part}"
        annual.write_text("\n".join(lines) + "\n", encoding="utf-8")
        rc = rebalance_growth.build_figure(staged)
        assert rc == 0
        rec_after = json.loads(
            _records.record_path(staged, FIGURE_NAME).read_text(encoding="utf-8")
        )
    assert rec_before["alt_text"] != rec_after["alt_text"], (
        "tampering the source data did not change the alt text: the record is not "
        "generated from the artifacts"
    )


def test_malformed_stamps_are_rejected() -> None:
    good = _records.stamp_string(
        "2026-09", "63b92cd", "analysis/figures/rebalance_growth.py"
    )
    assert _records.parse_stamp(good) is not None
    assert (
        _records.parse_stamp(
            "VINTAGE 2026-09 · BUILD-HEAD 63b92cd · analysis/figures/rebalance_growth.py"
        )
        is None
    )
    assert _records.parse_stamp(good.replace("63b92cd", "HEAD")) is None
    assert (
        _records.parse_stamp(good.replace("rebalance_growth.py", "foo bar.py")) is None
    )
    nogit = _records.stamp_string(
        "2026-09", "nogit", "analysis/figures/rebalance_growth.py"
    )
    nogit_parsed = _records.parse_stamp(nogit)
    assert nogit_parsed is not None
    assert nogit_parsed["build_head"] == "nogit"


# ---------------------------------------------------------------- geometry


def test_parse_dates_maps_month_to_calendar_year_fraction() -> None:
    """DATA.md §2: the decimal YYYY.MM codes are CALENDAR months.

    x must be year + (month-1)/12 and strictly monotone across the
    series; the pre-fix mapping regressed ~156 times per year at the
    11 -> 1 wrap.
    """
    import pandas as pd

    decimals = pd.read_csv(
        REPO_ROOT / "artifacts" / "series" / "canonical_60_40_monthly_v1.csv"
    )["date"]
    xs = rebalance_growth._parse_dates(decimals)
    diff = xs.diff().dropna()
    assert (diff > 0).all(), (
        "x mapping regresses: the date axis must be strictly monotone "
        f"(min diff {diff.min()})"
    )
    years = decimals.astype(float).astype(int)
    months = (
        (decimals - years).apply(lambda dt: round((dt - int(dt)) * 100)).clip(1, 12)
    )
    expected = years + (months - 1) / 12.0
    assert (xs == expected).all()
    i = decimals.index[decimals == 1871.10][0]  # 1871.1 == October 1871
    assert xs.loc[i] == 1871.0 + 9.0 / 12.0


def test_stamp_frame_bbox_matches_across_formats(built_root: Path) -> None:
    """The frame's corners are BAKED into figure fractions.

    The old dpi-dependent transform chain disagreed between the Agg
    and SVG backends (~18px on the bottom edge); the baked Polygon must
    land the same place in both exports. The SVG works in points
    (viewBox = canvas px x 72/DPI); both are converted to canvas px
    (y-down) before comparing.
    """
    import numpy as np
    from PIL import Image

    from analysis.figures import style

    pt_per_px = 72.0 / style.DPI
    viewBox = (
        f'viewBox="0 0 {style.CANVAS_PX[0] * pt_per_px:g} '
        f'{style.CANVAS_PX[1] * pt_per_px:g}"'
    )
    figdir = built_root / "artifacts" / "figures"
    svg = (figdir / f"{FIGURE_NAME}.svg").read_text(encoding="utf-8")
    assert viewBox in svg, (
        f"the canvas must be pinned to {style.CANVAS_PX} in the SVG viewBox"
    )
    frame_group = re.search(r'<g id="release-stamp-frame">(.*?)</g>', svg, re.DOTALL)
    assert frame_group is not None, "the frame must carry the release-stamp-frame gid"
    path_d = re.search(r'd="([^"]+)"', frame_group.group(1))
    assert path_d is not None, "the frame group must contain a path"
    nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", path_d.group(1))]
    assert len(nums) >= 8 and len(nums) % 2 == 0, (
        f"frame path must carry at least 4 corners, got {len(nums) / 2} points"
    )
    corners = list(zip(nums[0::2], nums[1::2]))  # closed paths repeat p0
    svg_bbox = tuple(
        v * (style.DPI / 72.0)
        for v in (
            min(x for x, _ in corners),
            min(y for _, y in corners),
            max(x for x, _ in corners),
            max(y for _, y in corners),
        )
    )  # SVG pts -> canvas px

    contract = json.loads(
        (built_root / "config" / "pairings_contract.json").read_text(encoding="utf-8")
    )
    accent = contract["tokens"]["accent-red"]
    target = tuple(int(accent[i : i + 2], 16) for i in (1, 3, 5))
    arr = np.asarray(Image.open(figdir / f"{FIGURE_NAME}.png").convert("RGB"))
    mask = (arr == np.array(target)).all(axis=2)
    ys, xs = np.where(mask)
    assert len(xs), "no accent-red pixels in the PNG"
    png_bbox = (float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max()))

    # The 2px frame's core pixels sit within a pixel of the baked
    # corners; 2px tolerance absorbs anti-aliasing on both sides.
    for where, (s, p) in enumerate(zip(svg_bbox, png_bbox)):
        assert abs(s - p) < 2.0, (
            f"stamp frame bbox disagrees across formats (side {where}): "
            f"SVG {svg_bbox} vs PNG {png_bbox}"
        )


def test_build_head_is_the_git_short_head(tmp_path: Path) -> None:
    """First BUILD-HEAD chain link: a .git root resolves to short HEAD."""
    import subprocess

    staged = tmp_path / "repo"
    _stage_repo(staged)
    for args in (
        ("init", "-q"),
        ("config", "user.email", "test@example.com"),
        ("config", "user.name", "test"),
        ("add", "-A"),
        ("commit", "-q", "-m", "seed"),
    ):
        subprocess.run(
            ["git", "-C", str(staged), *args], check=True, capture_output=True
        )
    head = subprocess.run(
        ["git", "-C", str(staged), "rev-parse", "--short", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    rc = rebalance_growth.build_figure(staged)
    assert rc == 0
    parsed = _records.parse_stamp(_record(staged)["stamp"])
    assert parsed is not None
    assert parsed["build_head"] == head
