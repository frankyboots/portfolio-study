"""Locked figure-style tests (story 1.6).

Proves the style lock: the canvas/dpi/stamp/dash constants, the
contract-sourced color tokens (no hex literals in figure code), the
vendored-font byte pins, the WCAG helpers against known pairs, the
measurement helpers tracking real renderer extents, and the
cross-process double-render byte equality of a figure build.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from analysis.figures import accessibility, style

# ---------------------------------------------------------------- constants


def test_canvas_dpi_and_scale_are_locked() -> None:
    assert style.CANVAS_PX == (1200, 800)
    assert style.DPI == 240
    # figsize is the canvas at the locked dpi: 1200 px / 240 dpi = 5 in wide.
    assert style.FIGSIZE_IN[0] == pytest.approx(style.CANVAS_PX[0] / style.DPI)
    assert style.FIGSIZE_IN[1] == pytest.approx(style.CANVAS_PX[1] / style.DPI)
    assert style.CANVAS_TO_DISPLAY == pytest.approx(375.0 / 1200.0)


def test_stamp_rect_and_rotation_are_locked() -> None:
    x0, y0, x1, y1 = style.STAMP_RECT_PX
    assert (x0, y0) == (24, 24)
    assert x1 > x0 and y1 > y0
    assert style.STAMP_ROTATION_DEG == -2.0
    assert style.STAMP_BORDER_PX == 2.0


def test_dash_ladder_is_locked() -> None:
    assert style.dash_style("solid") == ("-", 2.5)
    assert style.dash_style("dashed") == ("--", 2.0)
    assert style.dash_style("dash-dot") == ("-.", 2.0)
    assert style.dash_style("dotted") == (":", 2.0)
    with pytest.raises(KeyError):
        style.dash_style("long-dashed")


# ---------------------------------------------------------------- contract


def test_tokens_come_from_the_contract() -> None:
    import json

    doc = json.loads(
        (REPO_ROOT / "config" / "pairings_contract.json").read_text(encoding="utf-8")
    )
    contract = style.load_contract()
    assert contract == doc
    # style.token resolves through the contract, not a hardcoded copy.
    for name, hex_value in {**doc["tokens"], **doc["grounds"]}.items():
        assert style.token(name) == hex_value
    assert style.token("paper") == "#faf6ea"
    assert style.token("data-good") == "#2e5a24"


def test_pairing_row_lookup() -> None:
    row = style.pairing_row("ink", "paper")
    assert row is not None
    assert row["fg"] == "ink"
    assert row["on"] == "paper"
    assert row["ratio"] == 18.41
    assert style.pairing_row("ink", "dark") is None


def test_no_hex_color_literals_in_figure_code() -> None:
    """No figure module may carry a raw #rrggbb literal: colors are contract tokens."""
    hex_literal = re.compile(r"['\"]#[0-9a-fA-F]{6}['\"]")
    for source in sorted((REPO_ROOT / "analysis" / "figures").glob("*.py")):
        text = source.read_text(encoding="utf-8")
        assert not hex_literal.search(text), (
            f"{source.name} carries a hex color literal; colors come from the "
            "pairings contract"
        )


# ---------------------------------------------------------------- fonts


def test_vendored_fonts_match_the_readme_pins() -> None:
    """Each vendored TTF byte-matches the sha256 recorded in config/fonts/README.md."""
    readme = (REPO_ROOT / "config" / "fonts" / "README.md").read_text(encoding="utf-8")
    pins = {
        m.group(1): m.group(2).lower()
        for m in re.finditer(
            r"\|\s*`([A-Za-z0-9\-]+\.ttf)`\s*\|\s*[^|]+\|\s*[^|]+\|\s*`([0-9a-f]{64})`",
            readme,
        )
    }
    assert set(pins) == set(style.VENDORED_FONTS), (
        "README pin table drifted from style.VENDORED_FONTS"
    )
    for name, digest in pins.items():
        blob = (REPO_ROOT / "config" / "fonts" / name).read_bytes()
        assert hashlib.sha256(blob).hexdigest() == digest, f"{name} byte pin drifted"


def test_apply_style_locks_families_and_svg_paths() -> None:
    style.apply_style()
    import matplotlib

    # The serif category is locked to the single vendored face.
    family = matplotlib.rcParams["font.family"]
    assert (family[0] if isinstance(family, list) else family) == "serif"
    assert matplotlib.rcParams["font.serif"] == [style.SERIF_FAMILY]
    assert matplotlib.rcParams["svg.fonttype"] == "path"
    assert matplotlib.rcParams["svg.hashsalt"] == style.SVG_HASHSALT
    assert matplotlib.rcParams["figure.facecolor"] == style.token("paper")
    assert matplotlib.rcParams["axes.facecolor"] == style.token("paper")
    assert matplotlib.rcParams["figure.dpi"] == style.DPI


# ---------------------------------------------------------------- WCAG math


def test_contrast_ratio_against_known_pairs() -> None:
    # ink on paper is the contract's recorded 18.41.
    assert accessibility.contrast_ratio("#0b0906", "#faf6ea") == pytest.approx(
        18.41, abs=0.01
    )
    # identical colors: ratio 1.0; white on black: ratio ~21.
    assert accessibility.contrast_ratio("#776c56", "#776c56") == pytest.approx(1.0)
    assert accessibility.contrast_ratio("#ffffff", "#000000") == pytest.approx(
        21.0, abs=0.1
    )
    # symmetric.
    assert accessibility.contrast_ratio("#0b0906", "#faf6ea") == pytest.approx(
        accessibility.contrast_ratio("#faf6ea", "#0b0906")
    )


def test_luminance_and_scaling_helpers() -> None:
    assert accessibility.hex_to_rgb("#2e5a24") == (0x2E, 0x5A, 0x24)
    with pytest.raises(ValueError):
        accessibility.hex_to_rgb("2e5a24")
    with pytest.raises(ValueError):
        accessibility.hex_to_rgb("#2e5a2")
    assert accessibility.display_px(8.0) == pytest.approx(2.5)
    assert accessibility.role_threshold("text-normal") == 4.5
    assert accessibility.role_threshold("decorative") == 0.0
    with pytest.raises(KeyError):
        accessibility.role_threshold("hero")
    # The pilot's two data hues are within the grayscale delta-L band,
    # which is exactly why they carry distinct dashes.
    d_good = accessibility.relative_luminance(accessibility.hex_to_rgb("#2e5a24"))
    d_neut = accessibility.relative_luminance(accessibility.hex_to_rgb("#5c554a"))
    assert abs(d_good - d_neut) < accessibility.GRAYSCALE_DL_MAX


# ---------------------------------------------------------------- measurement


def test_measure_text_px_tracks_real_extents() -> None:
    """The measurement helper must follow the renderer, not a declared constant."""
    style.apply_style()
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=style.FIGSIZE_IN, dpi=style.DPI)
    small = ax.text(0.5, 0.5, "M", size=10.0, family=style.SERIF_FAMILY)
    big = ax.text(0.2, 0.5, "M", size=20.0, family=style.SERIF_FAMILY)
    renderer = fig.canvas.get_renderer()  # type: ignore[attr-defined]
    small_px = style.measure_text_px(small)
    big_px = style.measure_text_px(big)
    # Same glyph at double the point size measures ~double the extent.
    assert big_px == pytest.approx(2.0 * small_px, rel=0.05)
    assert small_px > 0
    # And the reported value is the renderer extent, not a floor constant.
    extent = small.get_window_extent(renderer)
    assert small_px == pytest.approx(extent.height)
    plt.close(fig)


def test_measure_line_px_tracks_line_width() -> None:
    style.apply_style()
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=style.FIGSIZE_IN, dpi=style.DPI)
    (thin,) = ax.plot([0, 1], [0, 1], linewidth=1.0)
    (thick,) = ax.plot([0, 1], [0, 1], linewidth=2.5)
    thin_px = style.measure_line_px(thin)
    thick_px = style.measure_line_px(thick)
    assert thick_px == pytest.approx(2.5 * thin_px, rel=0.1)
    assert thin_px > 0
    plt.close(fig)


# ---------------------------------------------------------------- byte stability


@pytest.fixture(scope="module")
def staged_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A .git-less repo-shaped root whose builder inputs never change."""
    staged = tmp_path_factory.mktemp("style-render") / "repo"
    for name in ("analysis", "config", "artifacts"):
        import shutil

        shutil.copytree(
            REPO_ROOT / name,
            staged / name,
            ignore=shutil.ignore_patterns("__pycache__", "fontlist*.json"),
        )
    # Drop the committed exports: the double-render test renders from scratch.
    figs = staged / "artifacts" / "figures"
    if figs.is_dir():
        for p in figs.iterdir():
            p.unlink()
    return staged


def _render_once(root: Path) -> dict[str, bytes]:
    driver = (
        f"import sys\n"
        f"sys.path.insert(0, {str(root)!r})\n"
        f"from pathlib import Path\n"
        f"from analysis.figures import registry\n"
        f"raise SystemExit(registry.build_all(Path({str(root)!r})))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", driver],
        capture_output=True,
        text=True,
        check=False,  # intentional: the exit code is asserted
    )
    assert proc.returncode == 0, proc.stderr
    figs = root / "artifacts" / "figures"
    return {p.name: p.read_bytes() for p in sorted(figs.iterdir())}


def test_cross_process_double_render_byte_equality(staged_root: Path) -> None:
    """Two fresh processes rendering the same inputs emit identical bytes."""
    first = _render_once(staged_root)
    assert first, "the build produced no exports"
    for name in first:  # wipe, re-render in a second process
        (staged_root / "artifacts" / "figures" / name).unlink()
    second = _render_once(staged_root)
    assert set(first) == set(second)
    for name, blob in first.items():
        assert second[name] == blob, f"{name} is not byte-stable across processes"
    # .git-less root with no manifest: the stamp carries the nogit sentinel.
    record = next(v for k, v in first.items() if k.endswith(".figure.json"))
    assert b"BUILD-HEAD nogit" in record
