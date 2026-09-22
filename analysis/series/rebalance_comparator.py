"""Calendar-year-end-rebalanced 60/40 comparator and rebalance-diff builder.

Composes the shared leg engine (:mod:`.legs`) -- the same endpoint walk,
mid-series guard, BM-identity cross-check, and per-month leg factors the
monthly canonical series consumes -- with the calendar-year-end
rebalancing rule, and emits byte-deterministic, versioned artifacts:

- ``artifacts/series/canonical_60_40_annual_v1.csv`` -- header
  ``date,real,nominal``; same row semantics as the monthly artifact
  (zero-padded ``YYYY.MM`` cells, ``repr()`` values, UTF-8, LF, final
  newline).
- ``artifacts/series/canonical_60_40_annual_v1.meta.json`` -- the sidecar
  metadata under the data-artifact schema contract (owner, units, index, shape
  family, serialization, vintage stamp, provisional-tail record,
  data-quality notes, row count).
- ``artifacts/series/canonical_60_40_rebalance_diff_v1.csv`` -- header
  ``date,real,nominal``; values = annual-rebalanced level minus
  monthly-rebalanced level (growth-index points, decimal).
- ``artifacts/series/canonical_60_40_rebalance_diff_v1.meta.json`` -- the
  sidecar; its ``summary`` block is a derived re-statement of the diff
  CSV (terminal diff, max-abs diff and its month, per column).

Annual-rebalance semantics:

- Weights reset to 0.6/0.4 for the first return month of each calendar
  year: the January return consumes reset weights, the seed month
  1871.01 starts at 0.6/0.4, and the first reset event is 1872.01.
- Within the year the weights drift with leg growth: month factor
  ``g = w_eq * g_eq + w_b * g_b``, then ``w_eq <- w_eq * g_eq / g`` and
  ``w_b <- w_b * g_b / g``.
- The real and nominal series each track their own drifting weights on
  their own legs; both indices seed at 1.0 at 1871.01.

The difference artifact is computed in-memory from the two
constructions of the one pinned vintage -- never read back from the
committed monthly CSV.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from . import canonical_60_40, shiller_io
from .canonical_60_40 import BuildError, SeriesResult, serialize_csv
from .legs import LegSet, build_legs, label
from .shiller_io import Vintage

ANNUAL_CSV_NAME = "canonical_60_40_annual_v1.csv"
ANNUAL_META_NAME = "canonical_60_40_annual_v1.meta.json"
DIFF_CSV_NAME = "canonical_60_40_rebalance_diff_v1.csv"
DIFF_META_NAME = "canonical_60_40_rebalance_diff_v1.meta.json"
ARTIFACT_DIR = ("artifacts", "series")

_EQ_WEIGHT = 0.6
_BOND_WEIGHT = 0.4

#: The pinned data-quality note shared with the monthly sidecars.
_DATA_QUALITY_NOTES = [
    (
        "DATA.md §7: the 2025.10 CPI value is Shiller's fill-in; BLS never "
        "released October 2025 CPI (2025 lapse in appropriations). 2026.08 "
        "and 2026.09 CPI values are Shiller estimates."
    ),
]


def annual_from_legs(legs: LegSet) -> SeriesResult:
    """Apply the calendar-year-end rebalancing rule to the shared leg factors.

    Both indices are seeded at 1.0 in the seed month with 0.6/0.4
    weights; the weights reset to 0.6/0.4 for the first return month of
    each calendar year (the January return consumes reset weights) and
    drift with leg growth within the year. Each series tracks its own
    weights on its own legs.
    """
    real = [1.0]
    nominal = [1.0]
    we_r = _EQ_WEIGHT
    wb_r = _BOND_WEIGHT
    we_n = _EQ_WEIGHT
    wb_n = _BOND_WEIGHT
    for m in legs.months:
        if m.month == 1:
            we_r = _EQ_WEIGHT
            wb_r = _BOND_WEIGHT
            we_n = _EQ_WEIGHT
            wb_n = _BOND_WEIGHT
        g_r = we_r * m.g_eq_real + wb_r * m.g_bond_real
        g_n = we_n * m.g_eq_nom + wb_n * m.g_bond_nom
        real.append(real[-1] * g_r)
        nominal.append(nominal[-1] * g_n)
        we_r = we_r * m.g_eq_real / g_r
        wb_r = wb_r * m.g_bond_real / g_r
        we_n = we_n * m.g_eq_nom / g_n
        wb_n = wb_n * m.g_bond_nom / g_n

    labels = (legs.seed_label, *tuple(m.label for m in legs.months))
    return SeriesResult(
        end_index=legs.end_index,
        labels=labels,
        real=tuple(real),
        nominal=tuple(nominal),
        excluded=legs.excluded,
    )


def diff_from_series(annual: SeriesResult, monthly: SeriesResult) -> SeriesResult:
    """Compute the in-memory difference artifact: annual level minus monthly level.

    Both conventions are constructions of the one pinned vintage in the
    same process; the diff is never read back from the committed monthly
    CSV.
    """
    return SeriesResult(
        end_index=annual.end_index,
        labels=annual.labels,
        real=tuple(a - m for a, m in zip(annual.real, monthly.real)),
        nominal=tuple(a - m for a, m in zip(annual.nominal, monthly.nominal)),
    )


def _summary_column(
    labels: tuple[str, ...], diff: tuple[float, ...]
) -> dict[str, object]:
    """The summary block for one column: a re-statement of the diff values."""
    k = max(range(len(diff)), key=lambda i: abs(diff[i]))
    return {
        "terminal_diff": diff[-1],
        "max_abs_diff": abs(diff[k]),
        "max_abs_diff_month": labels[k],
    }


def serialize_annual_meta(v: Vintage, result: SeriesResult) -> bytes:
    """Pinned sidecar serialization: json.dumps(indent=2, sort_keys=True) + newline."""
    meta: dict[str, object] = {
        "name": "canonical_60_40_annual_v1",
        "version": 1,
        "owner": "analysis.series.rebalance_comparator",
        "units": {
            "real": (
                "growth index, decimal (calendar-year-end rebalanced 60/40 "
                "total return, real; base 1.0 at 1871.01)"
            ),
            "nominal": (
                "growth index, decimal (calendar-year-end rebalanced 60/40 "
                "total return, nominal; base 1.0 at 1871.01)"
            ),
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
        "data_quality_notes": list(_DATA_QUALITY_NOTES),
        "row_count": len(result.labels),
    }
    return (json.dumps(meta, indent=2, sort_keys=True) + "\n").encode("utf-8")


def serialize_diff_meta(v: Vintage, diff: SeriesResult) -> bytes:
    """Pinned sidecar serialization: json.dumps(indent=2, sort_keys=True) + newline.

    Carries the data-artifact schema keys plus a ``summary`` block that is a
    derived re-statement of the diff CSV (terminal diff, max-abs diff
    and its month, per column) -- not independent numbers.
    """
    meta: dict[str, object] = {
        "name": "canonical_60_40_rebalance_diff_v1",
        "version": 1,
        "owner": "analysis.series.rebalance_comparator",
        "units": {
            "real": (
                "growth-index points, decimal (annual-rebalanced level minus "
                "monthly-rebalanced level of the canonical 60/40; 0.0 at 1871.01)"
            ),
            "nominal": (
                "growth-index points, decimal (annual-rebalanced level minus "
                "monthly-rebalanced level of the canonical 60/40; 0.0 at 1871.01)"
            ),
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
        "row_count": len(diff.labels),
        "summary": {
            "real": _summary_column(diff.labels, diff.real),
            "nominal": _summary_column(diff.labels, diff.nominal),
        },
    }
    return (json.dumps(meta, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_artifacts(
    root: Path, v: Vintage, annual: SeriesResult, diff: SeriesResult
) -> None:
    out_dir = root.joinpath(*ARTIFACT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / ANNUAL_CSV_NAME).write_bytes(serialize_csv(annual))
    (out_dir / ANNUAL_META_NAME).write_bytes(serialize_annual_meta(v, annual))
    (out_dir / DIFF_CSV_NAME).write_bytes(serialize_csv(diff))
    (out_dir / DIFF_META_NAME).write_bytes(serialize_diff_meta(v, diff))


def build_comparator(root: Path) -> int:
    """Build the comparator artifacts under ``root/artifacts/``.

    Both conventions are constructed from the one pinned vintage in this
    process (one shared leg engine); the diff is in-memory, never read
    from the committed monthly CSV. Returns 0 on success; prints the
    named error to stderr and returns 1 on failure (missing file, sha
    mismatch, mid-series gap, identity violation).
    """
    try:
        vintage = shiller_io.load_vintage(root)
        legs = build_legs(vintage)
        monthly = canonical_60_40.monthly_from_legs(legs)
        annual = annual_from_legs(legs)
        diff = diff_from_series(annual, monthly)
        write_artifacts(root, vintage, annual, diff)
    except (shiller_io.VintageError, BuildError) as exc:
        print(f"comparator: {exc}", file=sys.stderr)
        return 1
    print(
        f"comparator: {ANNUAL_CSV_NAME} + {DIFF_CSV_NAME} "
        f"({len(annual.labels)} rows, "
        f"{annual.labels[0]} -> {annual.labels[-1]}, "
        f"{len(annual.excluded)} provisional month(s) excluded)"
    )
    return 0
