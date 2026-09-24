"""Metrics tests: the >=15% drawdown-episode artifacts (story 1.8 D1/D7).

Covers the episode-walk semantics on synthetic indexes (the boundary
trough counts inclusively, sub-15% dips produce nothing, an open
>=15% stretch at the tail keeps empty recovery fields, sub-peaks that
never reach a new high do not split the stretch), the pinned CSV +
sidecar serialization, byte determinism across rebuilds, value-level
tie to the committed artifacts, and the manifest's auto-registration of
the episodes entry from the sidecar.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

from analysis.metrics.drawdown import (
    CSV_NAME,
    META_NAME,
    NAME,
    build_episodes,
    find_episodes,
    serialize_csv,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
XLS = REPO_ROOT / "data" / "ie_data.xls"
MANIFEST_PY = REPO_ROOT / "scripts" / "manifest.py"
PASS_RESULTS = {n: "pass" for n in range(1, 9)}


def _require_vintage() -> None:
    if not XLS.is_file():
        pytest.skip(
            "data/ie_data.xls not present; re-pull per data/RUNLOG.md "
            "before running builder tests"
        )


def _dates(years: int, start_year: int = 2000) -> list[str]:
    labels: list[str] = []
    for i in range(years):
        y = start_year + i // 12
        m = i % 12 + 1
        labels.append(f"{y:04d}.{m:02d}")
    return labels


def test_trough_exactly_on_the_15pct_boundary_qualifies() -> None:
    """A worst trough sitting exactly at 15% depth counts (inclusive)."""
    values = [100.0, 85.0, 120.0]  # 1 - 85/100 = 0.15 exactly
    dates = _dates(3)
    eps = find_episodes(values, dates)
    assert len(eps) == 1
    assert eps[0].peak_date == dates[0] and eps[0].trough_date == dates[1]
    assert eps[0].recovery_date == dates[2]
    assert eps[0].depth >= 0.15 - 1e-12
    assert eps[0].peak_value == 100.0 and eps[0].trough_value == 85.0
    assert eps[0].recovery_value == 120.0


def test_sub_15pct_dip_produces_no_episode() -> None:
    values = [100.0, 88.0, 97.0, 100.0]  # deepest trough 12%
    dates = _dates(4)
    assert find_episodes(values, dates) == []


def test_open_15pct_episode_at_the_tail_keeps_empty_recovery_fields() -> None:
    """A qualifying drawdown still unrecovered at the series tail is
    returned with None recovery fields (the CSV leaves those cells
    empty)."""
    values = [100.0, 50.0, 60.0, 55.0]  # -50% and never back to 100
    dates = _dates(4)
    eps = find_episodes(values, dates)
    assert len(eps) == 1
    assert eps[0].recovery_date is None and eps[0].recovery_value is None
    assert eps[0].trough_date == dates[1] and eps[0].trough_value == 50.0
    out = serialize_csv(eps).decode("utf-8")
    lines = out.splitlines()
    assert lines[0] == (
        "peak_date,peak_value,trough_date,trough_value,"
        "recovery_date,recovery_value,depth"
    )
    assert lines[1] == f"{dates[0]},{100.0!r},{dates[1]},{50.0!r},,,{eps[0].depth!r}"


def test_sub_peak_that_never_reaches_the_new_high_does_not_split() -> None:
    """The 1929-style case: a bounce to 75 (below the 100 peak) does not
    close the stretch; the single episode keeps its earliest trough."""
    values = [100.0, 40.0, 75.0, 30.0, 110.0]
    dates = _dates(5)
    eps = find_episodes(values, dates)
    assert len(eps) == 1
    assert eps[0].trough_date == dates[3]  # 30, not 40 (earliest worst)
    assert eps[0].depth == 1.0 - 30.0 / 100.0


def test_two_episodes_across_a_recovered_peak() -> None:
    values = [100.0, 80.0, 100.0, 130.0, 104.0, 140.0]
    # first: 100 -> 80 (20%) -> back to 100; the peak then advances to
    # 130; second: 130 -> 104 (20%) -> 140.
    dates = _dates(6)
    eps = find_episodes(values, dates)
    assert [e.peak_date for e in eps] == [dates[0], dates[3]]
    assert [e.trough_date for e in eps] == [dates[1], dates[4]]
    assert [e.recovery_date for e in eps] == [dates[2], dates[5]]


def test_values_dates_length_mismatch_and_short_series_refuse() -> None:
    with pytest.raises(ValueError):
        find_episodes([1.0, 0.5], _dates(3))
    with pytest.raises(ValueError):
        find_episodes([1.0], _dates(1))


def test_build_twice_is_byte_identical_and_ties_to_committed(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    _require_vintage()

    def staged_root() -> Path:
        root = tmp_path_factory.mktemp("drawdown-root")
        (root / "data").mkdir()
        shutil.copy2(XLS, root / "data" / "ie_data.xls")
        # The episodes builder reads the committed series artifacts.
        shutil.copytree(
            REPO_ROOT / "artifacts" / "series", root / "artifacts" / "series"
        )
        return root

    def build_once() -> dict[str, bytes]:
        root = staged_root()
        assert build_episodes(root) == 0
        out_dir = root / "artifacts" / "metrics"
        return {
            CSV_NAME: (out_dir / CSV_NAME).read_bytes(),
            META_NAME: (out_dir / META_NAME).read_bytes(),
        }

    first = build_once()
    second = build_once()
    assert first == second, "rebuild of byte-identical inputs must be byte-identical"
    # Value-level tie to the committed artifacts: a construction
    # regression must fail here even if the serialization holds.
    committed = REPO_ROOT / "artifacts" / "metrics"
    assert first[CSV_NAME] == (committed / CSV_NAME).read_bytes(), (
        f"built {CSV_NAME} differs from the committed artifact; rebuild and "
        "re-commit only if the construction change is deliberate"
    )
    assert first[META_NAME] == (committed / META_NAME).read_bytes()


def test_sidecar_schema_and_vintage_copy() -> None:
    _require_vintage()
    meta = json.loads(
        (REPO_ROOT / "artifacts" / "metrics" / META_NAME).read_text("utf-8")
    )
    source_meta = json.loads(
        (
            REPO_ROOT / "artifacts" / "series" / "canonical_60_40_monthly_v1.meta.json"
        ).read_text("utf-8")
    )
    assert meta["name"] == NAME
    assert meta["version"] == 1
    assert meta["owner"] == "analysis.metrics.drawdown"
    assert meta["index"] == "YYYY.MM"
    assert meta["shape_family"] == "long-table"
    assert meta["episodes"]["threshold"] == 0.15
    assert meta["episodes"]["epsilon"] == 1e-9
    # The vintage stamp is the source sidecar's, verbatim (one Vintage
    # stamps the whole tree).
    assert meta["vintage"] == source_meta["vintage"]
    rows = (
        (REPO_ROOT / "artifacts" / "metrics" / CSV_NAME).read_text("utf-8").splitlines()
    )
    assert meta["row_count"] == len(rows) - 1
    assert meta["episodes"]["count"] == len(rows) - 1


def test_manifest_auto_registers_the_episodes_entry(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """HAPPY_PATH auto-registration: the manifest's AD-9 registry picks
    up the episodes sidecar without any authored entry."""
    _require_vintage()
    staged = tmp_path_factory.mktemp("drawdown-manifest")
    for name in ("analysis", "artifacts", "config", "scripts"):
        shutil.copytree(
            REPO_ROOT / name,
            staged / name,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    spec = importlib.util.spec_from_file_location("manifest_under_test", MANIFEST_PY)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    manifest = module.build_manifest(staged, PASS_RESULTS)
    entry = manifest["artifacts"][NAME]
    assert entry["name"] == NAME
    assert entry["data_path"] == f"artifacts/metrics/{CSV_NAME}"
    assert entry["meta_path"] == f"artifacts/metrics/{META_NAME}"
    import hashlib

    data = staged / "artifacts" / "metrics" / CSV_NAME
    assert entry["data_sha256"] == hashlib.sha256(data.read_bytes()).hexdigest()
    # All sidecars now: three series + one metrics.
    assert len(manifest["artifacts"]) == 4


def test_missing_source_csv_refuses_naming_the_series_stage(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _require_vintage()
    root = tmp_path / "root"
    (root / "artifacts" / "series").mkdir(parents=True)
    assert build_episodes(root) != 0
    captured = capsys.readouterr()
    assert "canonical_60_40_monthly_v1.csv" in captured.err
    assert "run the series stage first" in captured.err


def test_missing_source_sidecar_refuses(tmp_path: Path) -> None:
    _require_vintage()
    root = tmp_path / "root"
    series_dir = root / "artifacts" / "series"
    series_dir.mkdir(parents=True)
    shutil.copy2(
        REPO_ROOT / "artifacts" / "series" / "canonical_60_40_monthly_v1.csv",
        series_dir / "canonical_60_40_monthly_v1.csv",
    )
    assert build_episodes(root) != 0
