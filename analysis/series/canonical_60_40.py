"""Canonical monthly-rebalanced 60/40 total-return series builder.

Reads the sha256-pinned Shiller Vintage through :mod:`shiller_io` (the
sole xlrd owner) and emits byte-deterministic, versioned artifacts:

- ``artifacts/series/canonical_60_40_monthly_v1.csv`` -- header
  ``date,real,nominal``; zero-padded ``YYYY.MM`` date cells; values as
  Python ``repr()``; UTF-8, LF newlines, final newline.
- ``artifacts/series/canonical_60_40_monthly_v1.meta.json`` -- the sidecar
  metadata (artifact identity, owner, units, index convention, shape
  family, serialization constants, vintage stamp, provisional-tail
  record, data-quality notes, row count).

Construction conventions (all verified in data/DATA.md):

- Real legs: equity = RealTR growth (col 9); bond = BR growth (col 18).
- Nominal legs: equity month factor = ``(P + D/12) / P_prev``; bond
  month factor = col 17 (BM) shifted down one row -- month ``i`` uses
  ``BM[i-1]`` -- cross-checked against
  ``(BR[i]/BR[i-1]) * (CPI[i]/CPI[i-1])`` at rel-tol 1e-12.
- Monthly rebalance: factor = ``0.6 * eq + 0.4 * bond``; both indices
  seeded at 1.0 in the first month (1871.01).
- The series ends at the last month where every construction input
  (P, D, CPI, BR; BM[i-1] for nominal bonds) is present; trailing
  months with blank required inputs are excluded and recorded with
  reasons in the sidecar. A mid-series None in a required column
  fails the build, naming the month and column.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import shiller_io
from .shiller_io import Vintage

#: Rel tolerance for the BM-shift vs BR*CPI identity cross-check
#: (the suite's BM-identity tolerance; DATA.md §8).
BM_IDENTITY_REL_TOL = 1e-12

CSV_NAME = "canonical_60_40_monthly_v1.csv"
META_NAME = "canonical_60_40_monthly_v1.meta.json"
ARTIFACT_DIR = ("artifacts", "series")

_EQ_WEIGHT = 0.6
_BOND_WEIGHT = 0.4


class BuildError(Exception):
    """Raised on a construction-convention failure (gap, identity, tail)."""


def _label(ym: tuple[int, int]) -> str:
    """Zero-padded YYYY.MM label from a parsed (year, month) pair."""
    return f"{ym[0]}.{ym[1]:02d}"


@dataclass(frozen=True)
class SeriesResult:
    """In-memory construction of the canonical series."""

    end_index: int
    labels: tuple[str, ...]
    real: tuple[float, ...]
    nominal: tuple[float, ...]
    excluded: tuple[tuple[str, str], ...] = field(default=())


def _take(col: tuple[float | None, ...], i: int, name: str, label: str) -> float:
    """Return the non-None value at ``i``, else fail naming month and column.

    The pre-loop mid-series guard already guarantees presence for P/D/CPI/
    BR/BM inside the used range; this keeps the factor loop total and
    gives RT (not part of the content-driven endpoint rule) the same
    named failure.
    """
    value = col[i]
    if value is None:
        raise BuildError(f"mid-series gap at {label}: column '{name}' is blank")
    return value


def _month_inputs_ok(v: Vintage, i: int) -> list[str]:
    """Names of the required inputs missing at month ``i`` (empty = ok)."""
    missing = [
        name
        for name, col in (("P", v.P), ("D", v.D), ("CPI", v.CPI), ("BR", v.BR))
        if col[i] is None
    ]
    if i > 0 and v.BM[i - 1] is None:
        missing.append("BM (nominal bond factor)")
    return missing


def compute(v: Vintage) -> SeriesResult:
    """Compute the canonical real + nominal 60/40 series from one Vintage.

    Raises :class:`BuildError` on a mid-series None in a required
    column, on a BM/BR*CPI identity violation, or when the seed month
    lacks inputs.
    """
    n = len(v.dates)
    if n < 2:
        raise BuildError("need at least two data rows to build the series")

    # Content-driven endpoint: walk back over the trailing provisional
    # tail; the endpoint is a function of file content, never a constant.
    j = n - 1
    excluded: list[tuple[str, str]] = []
    while j > 0:
        missing = _month_inputs_ok(v, j)
        if not missing:
            break
        excluded.append(
            (_label(v.dates[j]), f"required input(s) missing: {', '.join(missing)}")
        )
        j -= 1
    if _month_inputs_ok(v, j):
        raise BuildError(
            f"seed month {_label(v.dates[0])} lacks required inputs: "
            f"{', '.join(_month_inputs_ok(v, 0))}"
        )
    excluded.reverse()

    # Mid-series guard: any None inside [0..j] is a build failure, not
    # a provisional exclusion.
    for i in range(j + 1):
        for name, col in (("P", v.P), ("D", v.D), ("CPI", v.CPI), ("BR", v.BR)):
            if col[i] is None:
                raise BuildError(
                    f"mid-series gap at {_label(v.dates[i])}: column '{name}' is blank"
                )
        if i > 0 and v.BM[i - 1] is None:
            raise BuildError(
                f"mid-series gap at {_label(v.dates[i])}: column 'BM (nominal bond factor, shifted)' is blank"
            )

    real = [1.0]
    nominal = [1.0]
    for i in range(1, j + 1):
        lab = _label(v.dates[i])
        prev = _label(v.dates[i - 1])
        rt_i = _take(v.RT, i, "RT (RealTR)", lab)
        rt_prev = _take(v.RT, i - 1, "RT (RealTR)", prev)
        br_i = _take(v.BR, i, "BR", lab)
        br_prev = _take(v.BR, i - 1, "BR", prev)
        cpi_i = _take(v.CPI, i, "CPI", lab)
        cpi_prev = _take(v.CPI, i - 1, "CPI", prev)
        p_i = _take(v.P, i, "P", lab)
        p_prev = _take(v.P, i - 1, "P", prev)
        d_i = _take(v.D, i, "D", lab)
        bm_prev = _take(v.BM, i - 1, "BM (nominal bond factor, shifted)", lab)

        # Cross-check the shifted BM against the BR*CPI identity
        # (guards both the one-month lead and the read) at machine
        # precision before it is consumed.
        identity = (br_i / br_prev) * (cpi_i / cpi_prev)
        if abs(bm_prev - identity) > BM_IDENTITY_REL_TOL * abs(identity):
            raise BuildError(
                f"BM identity violated at {lab}: BM[{i - 1}]={bm_prev!r} "
                f"vs BR*CPI={identity!r} (rel-tol {BM_IDENTITY_REL_TOL})"
            )

        real_factor = _EQ_WEIGHT * (rt_i / rt_prev) + _BOND_WEIGHT * (br_i / br_prev)
        nominal_factor = (
            _EQ_WEIGHT * ((p_i + d_i / 12) / p_prev) + _BOND_WEIGHT * bm_prev
        )
        real.append(real[-1] * real_factor)
        nominal.append(nominal[-1] * nominal_factor)

    labels = tuple(_label(v.dates[i]) for i in range(j + 1))
    return SeriesResult(
        end_index=j,
        labels=labels,
        real=tuple(real),
        nominal=tuple(nominal),
        excluded=tuple(excluded),
    )


def serialize_csv(result: SeriesResult) -> bytes:
    """Pinned CSV serialization: repr() floats, LF, final newline."""
    lines = ["date,real,nominal"]
    for label, rv, nv in zip(result.labels, result.real, result.nominal):
        lines.append(f"{label},{rv!r},{nv!r}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def serialize_meta(v: Vintage, result: SeriesResult) -> bytes:
    """Pinned sidecar serialization: json.dumps(indent=2, sort_keys=True) + newline."""
    meta: dict[str, object] = {
        "name": "canonical_60_40_monthly_v1",
        "version": 1,
        "owner": "analysis.series.canonical_60_40",
        "units": {
            "real": "growth index, decimal (monthly-rebalanced 60/40 total return, real; base 1.0 at 1871.01)",
            "nominal": "growth index, decimal (monthly-rebalanced 60/40 total return, nominal; base 1.0 at 1871.01)",
        },
        "index": "YYYY.MM",
        "shape_family": "long-table",
        "serialization": (
            "csv: utf-8, LF newlines, final newline, values via Python repr(); "
            "sidecar json: json.dumps(obj, indent=2, sort_keys=True) + trailing newline"
        ),
        "vintage": {
            "sha256": v.sha256,
            "last_row": _label(v.last_row),
            "k": v.k,
        },
        "excluded_provisional": [
            {"month": month, "reason": reason} for month, reason in result.excluded
        ],
        "data_quality_notes": [
            (
                "DATA.md §7: the 2025.10 CPI value is Shiller's fill-in; BLS never "
                "released October 2025 CPI (2025 lapse in appropriations). 2026.08 "
                "and 2026.09 CPI values are Shiller estimates."
            ),
        ],
        "row_count": len(result.labels),
    }
    return (json.dumps(meta, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_artifacts(root: Path, v: Vintage, result: SeriesResult) -> None:
    out_dir = root.joinpath(*ARTIFACT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / CSV_NAME).write_bytes(serialize_csv(result))
    (out_dir / META_NAME).write_bytes(serialize_meta(v, result))


def build_series(root: Path) -> int:
    """Build the canonical series artifacts under ``root/artifacts/``.

    Returns 0 on success; prints the named error to stderr and returns
    1 on failure (missing file, sha mismatch, mid-series gap, identity
    violation).
    """
    try:
        vintage = shiller_io.load_vintage(root)
        result = compute(vintage)
        write_artifacts(root, vintage, result)
    except (shiller_io.VintageError, BuildError) as exc:
        print(f"series: {exc}", file=sys.stderr)
        return 1
    print(
        f"series: {CSV_NAME} ({len(result.labels)} rows, "
        f"{result.labels[0]} -> {result.labels[-1]}, "
        f"{len(result.excluded)} provisional month(s) excluded)"
    )
    return 0
