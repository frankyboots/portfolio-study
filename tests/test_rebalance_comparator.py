"""Builder tests for the annual-rebalance comparator.

Covers the frozen annual-rebalance semantics with hand-computed exact
values on a synthetic Vintage (drift within the year + the January
reset to 0.6/0.4), build-twice byte identity of all four comparator
artifacts against a staged copy of the pinned vintage in tmp dirs, and
the content-driven endpoint / seed / diff-seed facts on this vintage.
The repo's committed artifacts are never rewritten by the suite.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from analysis.series import shiller_io
from analysis.series.canonical_60_40 import monthly_from_legs
from analysis.series.legs import build_legs
from analysis.series.rebalance_comparator import (
    ANNUAL_CSV_NAME,
    ANNUAL_META_NAME,
    DIFF_CSV_NAME,
    DIFF_META_NAME,
    annual_from_legs,
    build_comparator,
    diff_from_series,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
XLS = REPO_ROOT / "data" / "ie_data.xls"

COMPARATOR_FILES = (
    ANNUAL_CSV_NAME,
    ANNUAL_META_NAME,
    DIFF_CSV_NAME,
    DIFF_META_NAME,
)


def _require_vintage() -> None:
    if not XLS.is_file():
        pytest.skip(
            "data/ie_data.xls not present; re-pull per data/RUNLOG.md before running builder tests"
        )


def _staged_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A fresh repo-shaped root carrying a staged copy of the pinned vintage."""
    _require_vintage()
    root = tmp_path_factory.mktemp("comparator-root")
    (root / "data").mkdir()
    shutil.copy2(XLS, root / "data" / "ie_data.xls")
    return root


def _synthetic_vintage() -> shiller_io.Vintage:
    """Five months (1871.01, 1871.02, 1871.03, 1872.01, 1872.02) with
    binary-exact leg factors:

    - g_eq_real  = 1.5   (RT: 100, 150, 225, 337.5, 506.25)
    - g_bond_real = 0.5  (BR: 100, 50, 25, 12.5, 6.25)
    - g_eq_nom   = 1.25  (P: 100, 125, 156.25, 195.3125, 244.140625; D = 0)
    - g_bond_nom = 0.875 (BM[i] = (BR[i+1]/BR[i]) * (CPI[i+1]/CPI[i])
                         = 0.5 * 1.75; CPI: 100, 175, 306.25, 535.9375,
                         937.890625)

    So every leg factor is exact in binary and the BM identity holds to
    machine precision.
    """
    dates = ((1871, 1), (1871, 2), (1871, 3), (1872, 1), (1872, 2))
    n = len(dates)
    return shiller_io.Vintage(
        sha256=shiller_io.VINTAGE_SHA256,
        last_row=dates[-1],
        k=937.890625,
        dates=dates,
        P=tuple(100.0 * (1.25**i) for i in range(n)),
        D=tuple(0.0 for _ in range(n)),
        RT=tuple(100.0 * (1.5**i) for i in range(n)),
        CPI=tuple(100.0 * (1.75**i) for i in range(n)),
        BM=(0.875, 0.875, 0.875, 0.875, None),  # last row unused by the engine
        BR=tuple(100.0 * (0.5**i) for i in range(n)),
    )


def test_annual_drift_within_year_and_january_reset_exact() -> None:
    """Hand-computed drift within a year + the January reset to 0.6/0.4.

    With the constant leg factors above:
    - g1 (1871.02, seed weights 0.6/0.4) = 0.6*1.5 + 0.4*0.5 = 1.1
    - drifted 1871.03 factor = (9/11)*1.5 + (2/11)*0.5 = 29/22 (real)
    - 1872.01 (January) consumes reset weights -> g1 again
    - 1872.02 drifts from the reset -> the same 29/22 factor
    (nominal: g1 = 1.1, drifted factor = 199/176).
    """
    v = _synthetic_vintage()
    legs = build_legs(v)
    assert [m.month for m in legs.months] == [2, 3, 1, 2]
    assert legs.seed_label == "1871.01"
    assert all(m.g_eq_real == 1.5 for m in legs.months)
    assert all(m.g_bond_real == 0.5 for m in legs.months)
    assert all(m.g_eq_nom == 1.25 for m in legs.months)
    assert all(m.g_bond_nom == 0.875 for m in legs.months)

    result = annual_from_legs(legs)
    assert list(result.labels) == [
        "1871.01",
        "1871.02",
        "1871.03",
        "1872.01",
        "1872.02",
    ]

    # Hand-computed factors (the pinned formulas, step by step).
    g_r1 = 0.6 * 1.5 + 0.4 * 0.5  # 1871.02, seed weights 0.6/0.4
    g_n1 = 0.6 * 1.25 + 0.4 * 0.875
    we_r1 = 0.6 * 1.5 / g_r1  # 9/11
    wb_r1 = 0.4 * 0.5 / g_r1  # 2/11
    we_n1 = 0.6 * 1.25 / g_n1  # 15/22
    wb_n1 = 0.4 * 0.875 / g_n1  # 7/22
    g_r2 = we_r1 * 1.5 + wb_r1 * 0.5  # 1871.03, drifted weights -> 29/22
    g_n2 = we_n1 * 1.25 + wb_n1 * 0.875  # -> 199/176
    g_r3 = 0.6 * 1.5 + 0.4 * 0.5  # 1872.01: January reset back to 0.6/0.4
    g_n3 = 0.6 * 1.25 + 0.4 * 0.875
    g_r4 = we_r1 * 1.5 + wb_r1 * 0.5  # 1872.02: drifts from the reset again
    g_n4 = we_n1 * 1.25 + wb_n1 * 0.875

    # The hand-computed values, documented to machine precision.
    assert abs(g_r1 - 1.1) < 1e-15 and abs(g_n1 - 1.1) < 1e-15
    assert abs(g_r2 - 29 / 22) < 1e-15
    assert abs(g_n2 - 199 / 176) < 1e-15
    assert abs(g_r3 - g_r1) < 1e-15, "the January return must consume reset weights"
    assert abs(g_r2 - g_r1) > 1e-12, "drift within the year must change the factor"

    exp_real = [1.0]
    exp_nom = [1.0]
    for gr, gn in ((g_r1, g_n1), (g_r2, g_n2), (g_r3, g_n3), (g_r4, g_n4)):
        exp_real.append(exp_real[-1] * gr)
        exp_nom.append(exp_nom[-1] * gn)
    assert list(result.real) == exp_real
    assert list(result.nominal) == exp_nom


def test_monthly_reimposes_weights_every_month_from_the_same_legs() -> None:
    """The monthly rule on the same legs: the seed factor every month,
    i.e. it must NOT drift within the year (the conventions' divergence
    is the rebalancing rule alone).
    """
    legs = build_legs(_synthetic_vintage())
    result = monthly_from_legs(legs)
    g_r1 = 0.6 * 1.5 + 0.4 * 0.5
    g_n1 = 0.6 * 1.25 + 0.4 * 0.875
    exp_real = [1.0]
    exp_nom = [1.0]
    for _ in range(4):
        exp_real.append(exp_real[-1] * g_r1)
        exp_nom.append(exp_nom[-1] * g_n1)
    assert list(result.real) == exp_real
    assert list(result.nominal) == exp_nom
    annual = annual_from_legs(legs)
    # The first return month (both on 0.6/0.4) agrees; drift starts after.
    assert result.real[1] == annual.real[1] and result.nominal[1] == annual.nominal[1]
    assert result.real[2] != annual.real[2]


def test_diff_is_annual_minus_monthly_in_memory() -> None:
    legs = build_legs(_synthetic_vintage())
    monthly = monthly_from_legs(legs)
    annual = annual_from_legs(legs)
    diff = diff_from_series(annual, monthly)
    assert diff.labels == annual.labels
    assert diff.real[0] == 0.0 and diff.nominal[0] == 0.0
    assert all(a - m == d for a, m, d in zip(annual.real, monthly.real, diff.real))
    assert all(
        a - m == d for a, m, d in zip(annual.nominal, monthly.nominal, diff.nominal)
    )


def test_build_twice_is_byte_identical_for_all_four_files(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    def build_once() -> dict[str, bytes]:
        root = _staged_root(tmp_path_factory)
        assert build_comparator(root) == 0
        out_dir = root / "artifacts" / "series"
        return {name: (out_dir / name).read_bytes() for name in COMPARATOR_FILES}

    first = build_once()
    second = build_once()
    assert first == second, (
        "rebuild of byte-identical repo state + raw file must be byte-identical"
    )

    # Value-level tie to the committed artifacts: a construction
    # regression must fail here even if the internal checks hold.
    committed = REPO_ROOT / "artifacts" / "series"
    for name in COMPARATOR_FILES:
        assert first[name] == (committed / name).read_bytes(), (
            f"built {name} differs from the committed artifact; rebuild and "
            "re-commit only if the construction change is deliberate"
        )


def test_vintage_facts_endpoint_seed_and_diff_seed(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    root = _staged_root(tmp_path_factory)
    assert build_comparator(root) == 0
    out_dir = root / "artifacts" / "series"

    annual_lines = (out_dir / ANNUAL_CSV_NAME).read_text(encoding="utf-8").splitlines()
    assert annual_lines[0] == "date,real,nominal"
    assert len(annual_lines) == 1 + 1866
    assert annual_lines[1] == "1871.01,1.0,1.0"
    # Content-driven endpoint on this vintage: 2026.06 (D/E blank 2026.07-09).
    assert annual_lines[-1].startswith("2026.06,")

    diff_lines = (out_dir / DIFF_CSV_NAME).read_text(encoding="utf-8").splitlines()
    assert diff_lines[0] == "date,real,nominal"
    assert diff_lines[1] == "1871.01,0.0,0.0"
    assert len(diff_lines) == 1 + 1866

    ann_meta = json.loads((out_dir / ANNUAL_META_NAME).read_text(encoding="utf-8"))
    assert ann_meta["row_count"] == 1866
    assert [e["month"] for e in ann_meta["excluded_provisional"]] == [
        "2026.07",
        "2026.08",
        "2026.09",
    ]
    assert ann_meta["vintage"]["sha256"] == shiller_io.VINTAGE_SHA256

    diff_meta = json.loads((out_dir / DIFF_META_NAME).read_text(encoding="utf-8"))
    assert diff_meta["row_count"] == 1866
    # The summary block is a derived re-statement of the diff CSV.
    dates = [line.split(",")[0] for line in diff_lines[1:]]
    real = [float(line.split(",")[1]) for line in diff_lines[1:]]
    nominal = [float(line.split(",")[2]) for line in diff_lines[1:]]
    for col, values in (("real", real), ("nominal", nominal)):
        s = diff_meta["summary"][col]
        assert s["terminal_diff"] == values[-1]
        k = max(range(len(values)), key=lambda i: abs(values[i]))
        assert s["max_abs_diff"] == abs(values[k])
        assert s["max_abs_diff_month"] == dates[k]


def test_diff_values_equal_annual_minus_monthly_on_this_vintage(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """The committed diff must equal the in-memory annual-minus-monthly
    construction of the pinned vintage, row for row (no read-from-CSV).
    """
    root = _staged_root(tmp_path_factory)
    assert build_comparator(root) == 0
    out_dir = root / "artifacts" / "series"
    annual_lines = (
        (out_dir / ANNUAL_CSV_NAME).read_text(encoding="utf-8").splitlines()[1:]
    )
    diff_lines = (out_dir / DIFF_CSV_NAME).read_text(encoding="utf-8").splitlines()[1:]

    vintage = shiller_io.load_vintage(root)
    monthly = monthly_from_legs(build_legs(vintage))
    for row, m_real, m_nom, drow in zip(
        annual_lines, monthly.real, monthly.nominal, diff_lines
    ):
        a_real, a_nom = (float(x) for x in row.split(",")[1:])
        d_real, d_nom = (float(x) for x in drow.split(",")[1:])
        assert a_real - m_real == d_real
        assert a_nom - m_nom == d_nom


def test_sha_mismatch_fails_naming_expected_and_actual_without_writing_artifacts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _require_vintage()
    root = tmp_path / "root"
    (root / "data").mkdir(parents=True)
    blob = XLS.read_bytes()
    tampered = blob[:1000] + b"\x00" + blob[1001:]
    (root / "data" / "ie_data.xls").write_bytes(tampered)

    assert build_comparator(root) != 0
    captured = capsys.readouterr()
    assert shiller_io.VINTAGE_SHA256 in captured.err
    assert hashlib.sha256(tampered).hexdigest() in captured.err
    assert not (root / "artifacts").exists(), (
        "no artifact may be written on a pin mismatch"
    )


def test_missing_file_fails_naming_the_repull_procedure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert build_comparator(tmp_path) != 0
    captured = capsys.readouterr()
    assert "data/RUNLOG.md" in captured.err
    assert "ie_data.xls" in captured.err
