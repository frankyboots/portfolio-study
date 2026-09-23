"""Builder tests for the canonical monthly 60/40 series.

Covers the builder's edge cases: build-twice byte identity (repro
contract), sha256 pin mismatch, missing file, mid-series None naming
month + column, the content-driven provisional endpoint on this
vintage, and the pinned zero-padded YYYY.MM CSV format. Builds run
against a staged copy of the pinned vintage in tmp dirs -- the repo's
committed artifacts are never rewritten by the suite.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from analysis.series import shiller_io
from analysis.series.canonical_60_40 import (
    CSV_NAME,
    META_NAME,
    BuildError,
    build_series,
    compute,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
XLS = REPO_ROOT / "data" / "ie_data.xls"

pytestmark = pytest.mark.skipif(
    not XLS.is_file(),
    reason="data/ie_data.xls not present; re-pull per data/RUNLOG.md before running builder tests",
)


def _staged_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A fresh repo-shaped root carrying a staged copy of the pinned vintage."""
    root = tmp_path_factory.mktemp("vintage-root")
    (root / "data").mkdir()
    shutil.copy2(XLS, root / "data" / "ie_data.xls")
    return root


def test_build_series_happy_path_and_endpoint(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    root = _staged_root(tmp_path_factory)
    assert build_series(root) == 0

    csv_path = root / "artifacts" / "series" / CSV_NAME
    meta_path = root / "artifacts" / "series" / META_NAME
    assert csv_path.is_file() and meta_path.is_file()

    lines = csv_path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "date,real,nominal"
    assert len(lines) == 1 + 1866
    # Content-driven endpoint on this vintage: 2026.06 (D/E blank 2026.07-09).
    assert lines[-1].startswith("2026.06,")

    meta = meta_path.read_text(encoding="utf-8")
    assert meta.endswith("\n")

    obj = json.loads(meta)
    assert obj["row_count"] == 1866
    assert [e["month"] for e in obj["excluded_provisional"]] == [
        "2026.07",
        "2026.08",
        "2026.09",
    ]
    assert all("D" in e["reason"] for e in obj["excluded_provisional"])
    assert obj["vintage"]["last_row"] == "2026.09"
    assert obj["vintage"]["k"] == 333.8925
    assert obj["vintage"]["sha256"] == shiller_io.VINTAGE_SHA256


def test_yyyy_mm_zero_padded_seed_row(tmp_path_factory: pytest.TempPathFactory) -> None:
    root = _staged_root(tmp_path_factory)
    assert build_series(root) == 0
    first = (root / "artifacts" / "series" / CSV_NAME).read_text().splitlines()[1]
    # Zero-padded month, both indices seeded at 1.0 via repr().
    assert first == "1871.01,1.0,1.0"


def test_build_matches_committed_artifacts(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Value-level tie to the committed artifacts: a construction regression
    (e.g. D/12 dropped) must fail here even if the internal consistency
    checks still hold.
    """
    root = _staged_root(tmp_path_factory)
    assert build_series(root) == 0
    built = root / "artifacts" / "series"
    committed = REPO_ROOT / "artifacts" / "series"
    assert (built / CSV_NAME).read_bytes() == (committed / CSV_NAME).read_bytes(), (
        "built CSV differs from the committed artifact; rebuild and re-commit "
        "only if the construction change is deliberate"
    )
    assert (built / META_NAME).read_bytes() == (committed / META_NAME).read_bytes()


def test_build_twice_is_byte_identical(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    def build_once() -> tuple[bytes, bytes]:
        root = _staged_root(tmp_path_factory)
        assert build_series(root) == 0
        series_dir = root / "artifacts" / "series"
        return (series_dir / CSV_NAME).read_bytes(), (
            series_dir / META_NAME
        ).read_bytes()

    first = build_once()
    second = build_once()
    assert first == second, (
        "rebuild of byte-identical repo state + raw file must be byte-identical"
    )


def test_sha_mismatch_fails_naming_expected_and_actual(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "root"
    (root / "data").mkdir(parents=True)
    blob = XLS.read_bytes()
    tampered = blob[:1000] + b"\x00" + blob[1001:]
    (root / "data" / "ie_data.xls").write_bytes(tampered)

    assert build_series(root) != 0
    captured = capsys.readouterr()
    assert shiller_io.VINTAGE_SHA256 in captured.err
    assert hashlib.sha256(tampered).hexdigest() in captured.err
    assert not (root / "artifacts").exists(), (
        "no artifact may be written on a pin mismatch"
    )


def test_missing_file_fails_naming_the_repull_procedure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert build_series(tmp_path) != 0
    captured = capsys.readouterr()
    assert "data/RUNLOG.md" in captured.err
    assert "ie_data.xls" in captured.err


def test_mid_series_none_fails_naming_month_and_column() -> None:
    # Synthetic vintage: 12 valid months with D blank at 1871.06 (row 5,
    # strictly mid-series, not the trailing tail) -> build must fail.
    n = 12
    dates = tuple((1871, m) for m in range(1, n + 1))
    d = [1.0] * n
    d[5] = None
    v = shiller_io.Vintage(
        sha256=shiller_io.VINTAGE_SHA256,
        last_row=dates[-1],
        k=100.0,
        dates=dates,
        P=tuple(1.0 for _ in range(n)),
        D=tuple(d),
        RT=tuple(1.0 for _ in range(n)),
        CPI=tuple(100.0 for _ in range(n)),
        BM=tuple(1.0 for _ in range(n)),
        BR=tuple(1.0 for _ in range(n)),
        notes_row="",
    )
    with pytest.raises(BuildError, match=r"1871\.06.*'D'"):
        compute(v)


def test_mid_series_none_in_bm_shift_fails_naming_month_and_column() -> None:
    n = 12
    dates = tuple((1871, m) for m in range(1, n + 1))
    bm = [1.0] * n
    bm[4] = None  # month 1871.06's nominal bond factor = BM[i-1] = BM[4]
    v = shiller_io.Vintage(
        sha256=shiller_io.VINTAGE_SHA256,
        last_row=dates[-1],
        k=100.0,
        dates=dates,
        P=tuple(1.0 for _ in range(n)),
        D=tuple(1.0 for _ in range(n)),
        RT=tuple(1.0 for _ in range(n)),
        CPI=tuple(100.0 for _ in range(n)),
        BM=tuple(bm),
        BR=tuple(1.0 for _ in range(n)),
        notes_row="",
    )
    with pytest.raises(BuildError, match=r"1871\.06.*'BM"):
        compute(v)


def test_bm_identity_violation_fails() -> None:
    n = 12
    dates = tuple((1871, m) for m in range(1, n + 1))
    bm = [1.0] * n
    bm[1] = 1.5  # 1871.02's factor wildly off from BR*CPI = 1.0
    v = shiller_io.Vintage(
        sha256=shiller_io.VINTAGE_SHA256,
        last_row=dates[-1],
        k=100.0,
        dates=dates,
        P=tuple(1.0 for _ in range(n)),
        D=tuple(1.0 for _ in range(n)),
        RT=tuple(1.0 for _ in range(n)),
        CPI=tuple(100.0 for _ in range(n)),
        BM=tuple(bm),
        BR=tuple(1.0 for _ in range(n)),
        notes_row="",
    )
    with pytest.raises(BuildError, match=r"BM identity violated at 1871\.03"):
        compute(v)
