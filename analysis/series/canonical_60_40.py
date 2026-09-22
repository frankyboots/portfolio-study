"""Canonical monthly-rebalanced 60/40 total-return series builder.

Composes the shared leg engine (:mod:`.legs`) with the monthly
rebalancing rule (weights re-imposed to 0.6/0.4 every return month) and
emits byte-deterministic, versioned artifacts:

- ``artifacts/series/canonical_60_40_monthly_v1.csv`` -- header
  ``date,real,nominal``; zero-padded ``YYYY.MM`` date cells; values as
  Python ``repr()``; UTF-8, LF newlines, final newline.
- ``artifacts/series/canonical_60_40_monthly_v1.meta.json`` -- the sidecar
  metadata (artifact identity, owner, units, index convention, shape
  family, serialization constants, vintage stamp, provisional-tail
  record, data-quality notes, row count).

Construction conventions (all verified in data/DATA.md) live in the
shared leg engine (:mod:`.legs`); this module owns the monthly
rebalancing rule on top of the shared leg factors:

- Monthly rebalance: factor = ``0.6 * eq + 0.4 * bond`` every return
  month; both indices seeded at 1.0 in the first month (1871.01).
- The series endpoint, provisional-tail record, mid-series guards, and
  BM-identity cross-check come from :func:`.legs.build_legs` -- this
  module and the annual-rebalance comparator both consume that one
  engine, so their divergence is the rebalancing rule alone.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import shiller_io
from .legs import (
    BuildError,  # re-exported for the pinned public surface
    LegSet,
    build_legs,
    label,
)
from .shiller_io import Vintage

CSV_NAME = "canonical_60_40_monthly_v1.csv"
META_NAME = "canonical_60_40_monthly_v1.meta.json"
ARTIFACT_DIR = ("artifacts", "series")

_EQ_WEIGHT = 0.6
_BOND_WEIGHT = 0.4


@dataclass(frozen=True)
class SeriesResult:
    """In-memory construction of the canonical series."""

    end_index: int
    labels: tuple[str, ...]
    real: tuple[float, ...]
    nominal: tuple[float, ...]
    excluded: tuple[tuple[str, str], ...] = field(default=())


def monthly_from_legs(legs: LegSet) -> SeriesResult:
    """Apply the monthly rebalancing rule to the shared leg factors.

    Both indices are seeded at 1.0 in the seed month; every return
    month re-imposes the 0.6/0.4 weights, so each month factor is the
    weighted leg average ``0.6 * eq + 0.4 * bond``.
    """
    real = [1.0]
    nominal = [1.0]
    for m in legs.months:
        real_factor = _EQ_WEIGHT * m.g_eq_real + _BOND_WEIGHT * m.g_bond_real
        nominal_factor = _EQ_WEIGHT * m.g_eq_nom + _BOND_WEIGHT * m.g_bond_nom
        real.append(real[-1] * real_factor)
        nominal.append(nominal[-1] * nominal_factor)

    labels = (legs.seed_label, *tuple(m.label for m in legs.months))
    return SeriesResult(
        end_index=legs.end_index,
        labels=labels,
        real=tuple(real),
        nominal=tuple(nominal),
        excluded=legs.excluded,
    )


def compute(v: Vintage) -> SeriesResult:
    """Compute the canonical real + nominal 60/40 series from one Vintage.

    Raises :class:`BuildError` on a mid-series None in a required
    column, on a BM/BR*CPI identity violation, or when the seed month
    lacks inputs.
    """
    return monthly_from_legs(build_legs(v))


def serialize_csv(result: SeriesResult) -> bytes:
    """Pinned CSV serialization: repr() floats, LF, final newline."""
    lines = ["date,real,nominal"]
    for lbl, rv, nv in zip(result.labels, result.real, result.nominal):
        lines.append(f"{lbl},{rv!r},{nv!r}")
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
            "last_row": label(v.last_row),
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
