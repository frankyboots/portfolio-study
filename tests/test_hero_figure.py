"""Hero figure tests (story 1.8 D3/D7): the hero_real_growth construction.

Proves the hero's accuracy and export discipline: the record schema
(the same nine-key top-level shape as the pilot, the EXPERIENCE.md
alt-text v1 key set, the log-scale declaration), the min_px floor on
the band-hatch style declaration, the record's stamp vintage leg
against the source sidecars' vintage, byte-identical rebuilds on a
no-git staged root (deterministic exports: hash salt + vendored
fonts + locked canvas), the keep-out guards (the episode-count line
and the stamped block live inside STAMP_RECT_PX; a label that
intrudes fails the build), and the cross-artifact check (a tampered
episodes CSV refuses the build).
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from analysis.figures import _records, hero_real_growth
from analysis.figures.hero_real_growth import _band_x_extents

FIGURE_NAME = "hero_real_growth_v1"
SUFFIXES = (".png", ".svg", ".figure.json")


def _staged_copy_ignore(dirpath: str, dirnames: list[str]) -> list[str]:
    """Staged-copy filter: drop pycache and ONLY the exports dir, same
    precedent as the pilot test (the generated exports are excluded so
    the build regenerates them; the builder code stays)."""
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
    for stray in staged.glob("**/fontlist*.json"):
        stray.unlink()


def _fresh_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    staged = tmp_path_factory.mktemp("hero") / "repo"
    _stage_repo(staged)
    return staged


@pytest.fixture(scope="module")
def built_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A .git-less repo-shaped root with the hero built once in-process."""
    staged = _fresh_root(tmp_path_factory)
    rc = hero_real_growth.build_figure(staged)
    assert rc == 0, f"hero build failed on a clean staged root (exit {rc})"
    return staged


def _record(root: Path) -> dict:
    return json.loads(
        _records.record_path(root, FIGURE_NAME).read_text(encoding="utf-8")
    )


def test_record_top_level_schema(built_root: Path) -> None:
    rec = _record(built_root)
    # The nine-key record shape (same top-level contract as the pilot).
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
    assert rec["builder"] == hero_real_growth.SCRIPT_REL
    assert rec["canvas_px"] == {"width": 1200, "height": 800}
    # The two registered inputs, in declaration order: the growth index
    # first, the episodes second.
    assert rec["source_artifacts"] == [
        "canonical_60_40_monthly_v1",
        "60_40_drawdown_episodes_real_v1",
    ]
    assert [s["id"] for s in rec["series"]] == [
        "real_growth_line",
        "drawdown_bands",
    ]
    by_id = {s["id"]: s for s in rec["series"]}
    assert by_id["real_growth_line"]["role"] == "primary"
    assert by_id["real_growth_line"]["dash"] == "solid"
    assert by_id["real_growth_line"]["fg"] == "ink"
    assert by_id["drawdown_bands"]["role"] == "band"
    assert by_id["drawdown_bands"]["fg"] == "data-bad"
    # No hand-typed episode count anywhere: the count sentence in the
    # alt text must agree with the committed episodes CSV.
    rows = (
        (REPO_ROOT / "artifacts" / "metrics" / "60_40_drawdown_episodes_real_v1.csv")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    n = len(rows) - 1
    assert (
        f"{n} hatched bands mark the drawdown episodes" in rec["alt_text"]["alt_text"]
    )
    assert (
        f"{n} EPISODES >= 15%" not in rec["alt_text"]["alt_text"]
    )  # that is the keep-out line


def test_alt_text_is_the_v1_key_set_with_log_scale(built_root: Path) -> None:
    alt = _record(built_root)["alt_text"]
    assert set(alt) == {
        "alt_text",
        "axis",
        "chart_type",
        "extremes",
        "pairing_applies",
        "range",
        "series",
        "trend",
    }
    # The honest log declaration is the D3 contract.
    assert alt["axis"]["scale"] == "log"
    assert alt["chart_type"] == "line"
    assert alt["pairing_applies"] is False
    assert "log scale" in alt["alt_text"]
    assert "equal slopes are equal growth rates" in alt["trend"]
    assert [s["role"] for s in alt["series"]] == ["primary", "band"]
    # The range keeps the native YYYY.MM tokens.
    series = (
        (REPO_ROOT / "artifacts" / "series" / "canonical_60_40_monthly_v1.csv")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    first, last = series[1].split(",")[0], series[-1].split(",")[0]
    assert alt["range"]["start"] == first
    assert alt["range"]["end"] == last
    assert alt["range"]["period"] == "monthly"


def test_alt_text_extremes_computed_from_the_series(built_root: Path) -> None:
    """The alt text is generated from the artifacts, not pasted beside."""
    from analysis.figures.rebalance_growth import _fmt, _humanize_ym

    series = (
        (REPO_ROOT / "artifacts" / "series" / "canonical_60_40_monthly_v1.csv")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    dates = [line.split(",")[0] for line in series[1:]]
    values = [float(line.split(",")[1]) for line in series[1:]]
    i_min = min(range(len(values)), key=lambda i: values[i])
    i_max = max(range(len(values)), key=lambda i: values[i])
    alt = _record(built_root)["alt_text"]
    assert _fmt(values[i_min]) in alt["alt_text"]
    assert _humanize_ym(dates[i_min]) in alt["alt_text"]
    assert _fmt(values[i_max]) in alt["alt_text"]
    assert _humanize_ym(dates[i_max]) in alt["alt_text"]
    # The terminal-value clause: this vintage's maximum is the last row.
    if i_max == len(values) - 1:
        assert ", the terminal value" in alt["alt_text"]


def test_measurements_and_band_hatch_min_px_floor(built_root: Path) -> None:
    rec = _record(built_root)
    for measurement in rec["measurements"]:
        assert set(measurement) == {"element", "class", "render_px", "display_px"}
        assert measurement["render_px"] > 0
        assert measurement["display_px"] > 0
    classes = {m["class"] for m in rec["measurements"]}
    assert {"caption-class", "series-label", "series-line", "mono-stamp"} <= classes
    assert "band-hatch" in classes
    decls = {d["element"]: d for d in rec["style_declarations"]}
    # The D3 floor: the band hatch is a render-px contract riding a
    # declared min_px of 4px.
    assert decls["band_hatch"]["min_px"] == 4
    assert decls["band_hatch"]["role"] == "non-text"
    assert decls["count_line"]["fg"] == "accent-red"
    hatch = next(m for m in rec["measurements"] if m["element"] == "band_hatch")
    from analysis.figures import style

    assert hatch["render_px"] == style.BAND_HATCH_LINWIDTH_PX
    # Every band carries a measured year label and a swatch measurement.
    n = (
        len(
            (
                REPO_ROOT
                / "artifacts"
                / "metrics"
                / "60_40_drawdown_episodes_real_v1.csv"
            )
            .read_text(encoding="utf-8")
            .splitlines()
        )
        - 1
    )
    elements = {m["element"] for m in rec["measurements"]}
    for i in range(n):
        assert f"band_year_label_{i:02d}" in elements
        assert f"band_year_swatch_{i:02d}" in elements


def test_stamp_vintage_leg_matches_the_sidecars(built_root: Path) -> None:
    rec = _record(built_root)
    parsed = _records.parse_stamp(rec["stamp"])
    assert parsed is not None, f"stamp does not match the AD-6 schema: {rec['stamp']!r}"
    assert parsed["script"] == "analysis/figures/hero_real_growth.py"
    # The record's vintage leg is the source sidecars' vintage, verbatim
    # (one Vintage stamps the whole tree).
    assert parsed["vintage"] == _records.resolve_vintage(built_root)
    meta = json.loads(
        (
            built_root
            / "artifacts"
            / "metrics"
            / "60_40_drawdown_episodes_real_v1.meta.json"
        ).read_text(encoding="utf-8")
    )
    last_row = meta["vintage"]["last_row"]
    assert parsed["vintage"] == last_row[:4] + "-" + last_row[5:]


def test_rebuild_is_byte_identical_on_a_nogit_root(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Non-stamp stability: with no .git (BUILD-HEAD leg pinned to
    nogit) a second build is byte-identical across all three exports —
    the hash salt, the vendored fonts, and the locked canvas make the
    render deterministic."""
    staged = _fresh_root(tmp_path_factory)
    assert hero_real_growth.build_figure(staged) == 0
    figs = staged / "artifacts" / "figures"
    first = {
        suffix: (figs / f"{FIGURE_NAME}{suffix}").read_bytes() for suffix in SUFFIXES
    }
    assert hero_real_growth.build_figure(staged) == 0
    for suffix in SUFFIXES:
        assert (figs / f"{FIGURE_NAME}{suffix}").read_bytes() == first[suffix], (
            f"{suffix} was not byte-identical on a rebuild of unchanged inputs"
        )


def test_count_line_escaping_the_keep_out_fails(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The episode-count line must stay inside STAMP_RECT_PX: the
    runtime guard trips when the count extent leaves the band. The
    count text is lengthened (the stamp inherits only the count's x
    anchor and height, so it stays legal and only the count trips)."""
    staged = _fresh_root(tmp_path_factory)
    monkeypatch.setattr(
        hero_real_growth,
        "_count_line_text",
        lambda n: f"{n} EPISODES >= 15% OF THE GROWTH INDEX ACROSS THE FULL RANGE",
    )
    with pytest.raises(AssertionError, match="escapes the keep-out band"):
        hero_real_growth.build_figure(staged)


def test_growth_label_intruding_on_the_keep_out_fails(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A top-right label pulled over the keep-out band's x range fails
    the measured-intrusion guard (the label's real extent, not an
    assumed width). Anchored ha=right at 475px: the full ink box stays
    inside the band's x range (24-480) and on canvas, so the intrusion
    guard — not the canvas guard — is the one that must trip."""
    staged = _fresh_root(tmp_path_factory)
    monkeypatch.setattr(hero_real_growth, "GROWTH_LABEL_ANCHOR_PX", (475.0, 60.0))
    with pytest.raises(AssertionError, match="intrudes on the keep-out band"):
        hero_real_growth.build_figure(staged)


def test_tampered_episodes_csv_refuses_the_build(
    tmp_path_factory: pytest.TempPathFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    """The cross-artifact check: an episodes CSV whose values no longer
    re-derive from the series CSV must fail the build loudly."""
    staged = _fresh_root(tmp_path_factory)
    episodes = staged / "artifacts" / "metrics" / "60_40_drawdown_episodes_real_v1.csv"
    lines = episodes.read_text(encoding="utf-8").splitlines()
    parts = lines[1].split(",")
    parts[1] = repr(float(parts[1]) * 1.5)  # peak_value no longer matches the series
    lines[1] = ",".join(parts)
    episodes.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="does not match the series value"):
        hero_real_growth.build_figure(staged)


def test_zero_episode_artifact_builds_a_bandless_zero_count_chart(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """EPISODE_NONE, the builder side: a header-only episodes artifact
    builds a chart with NO bands and a keep-out count line that reads
    zero (checked in the SVG text comments and the record's alt text)."""
    staged = _fresh_root(tmp_path_factory)
    (staged / "artifacts" / "metrics" / "60_40_drawdown_episodes_real_v1.csv").write_text(
        "peak_date,peak_value,trough_date,trough_value,"
        "recovery_date,recovery_value,depth\n",
        encoding="utf-8",
    )
    assert hero_real_growth.build_figure(staged) == 0
    svg = (staged / "artifacts" / "figures" / f"{FIGURE_NAME}.svg").read_text(
        encoding="utf-8"
    )
    assert "0 EPISODES" in svg  # the keep-out count line reads zero
    assert "drawdown-band-0" not in svg  # no bands rendered
    rec = _record(staged)
    assert "0 hatched bands mark the drawdown episodes" in rec["alt_text"]["alt_text"]


def test_open_episode_band_extends_to_the_series_tail() -> None:
    """EPISODE_OPEN, the builder side: an episode with empty recovery
    cells bands from its peak to the LAST series month (the tail)."""
    import pandas as pd

    series = pd.DataFrame(
        {"date": ["2000.01", "2000.02", "2000.03"], "real": [1.0, 0.5, 0.6]}
    )
    x = pd.Series([2000.0, 2000.0 + 1 / 12, 2000.0 + 2 / 12])
    episodes = pd.DataFrame(
        {
            "peak_date": ["2000.01"],
            "peak_value": ["1.0"],
            "trough_date": ["2000.02"],
            "trough_value": ["0.5"],
            "recovery_date": [""],
            "recovery_value": [""],
            "depth": ["0.5"],
        }
    )
    extents = _band_x_extents(series, episodes, x)
    assert extents == [(2000.0, float(x.iloc[-1]))]


def test_missing_episodes_csv_refuses_naming_the_metrics_stage(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    staged = _fresh_root(tmp_path_factory)
    shutil.rmtree(staged / "artifacts" / "metrics")
    with pytest.raises(FileNotFoundError, match="run the metrics stage first"):
        hero_real_growth.build_figure(staged)


def test_build_all_registers_the_hero(tmp_path_factory: pytest.TempPathFactory) -> None:
    """The registry knows the hero: both registered builders build on a
    clean staged root and the hero lands next to the pilot."""
    from analysis.figures import registry

    assert "hero_real_growth_v1" in registry.FIGURE_BUILDERS
    assert "rebalance_growth_v1" in registry.FIGURE_BUILDERS
    assert sorted(registry.FIGURE_BUILDERS) == [
        "hero_real_growth_v1",
        "rebalance_growth_v1",
    ]
