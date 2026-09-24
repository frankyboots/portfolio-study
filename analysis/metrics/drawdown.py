"""Drawdown episodes for the canonical monthly 60/40 series, real terms.

Computes the peak-to-new-high drawdown episodes of the committed real
monthly growth index (``artifacts/series/canonical_60_40_monthly_v1.csv``,
``real`` column — base 1.0 at 1871.01, provisional tail already excluded
by the series builder) and emits byte-deterministic, versioned
artifacts under ``artifacts/metrics/``:

- ``60_40_drawdown_episodes_real_v1.csv`` -- header
  ``peak_date,peak_value,trough_date,trough_value,recovery_date,
  recovery_value,depth``; the same serialization discipline as the
  series CSVs (zero-padded ``YYYY.MM`` cells, ``repr()`` values, UTF-8,
  LF, final newline). An open episode (a >=15% drawdown still
  unrecovered at the series tail) leaves its recovery cells empty.
- ``60_40_drawdown_episodes_real_v1.meta.json`` -- the sidecar
  metadata under the data-artifact schema contract (owner, units, index,
  shape family, serialization, vintage stamp, the threshold + algorithm
  record, row count).

Episode definition (the threshold and the epsilon are recorded in the
sidecar, never re-derived): an episode is an underwater stretch, from a
peak month to the first month the index reaches a new high; it
qualifies when its worst trough depth (``1 - trough/peak``) is >= 0.15
INCLUSIVE (compared with the recorded tiny epsilon so a trough sitting
exactly on the boundary counts). Sub-peaks that never reach a new high
do not split the stretch.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

NAME = "60_40_drawdown_episodes_real_v1"
CSV_NAME = f"{NAME}.csv"
META_NAME = f"{NAME}.meta.json"
ARTIFACT_DIR = ("artifacts", "metrics")
OWNER = "analysis.metrics.drawdown"

SOURCE_CSV_NAME = "canonical_60_40_monthly_v1.csv"
SOURCE_META_NAME = "canonical_60_40_monthly_v1.meta.json"

#: The qualifying trough depth: an episode is a drawdown band when its
#: worst trough is at least 15% below the peak, inclusive.
THRESHOLD: float = 0.15

#: The recorded epsilon for the inclusive >= comparison: float noise at
#: the boundary must not flip an exactly-boundary trough out of the set.
EPS: float = 1e-9


@dataclass(frozen=True)
class Episode:
    """One qualifying peak-to-new-high underwater stretch."""

    peak_date: str
    peak_value: float
    trough_date: str
    trough_value: float
    depth: float
    #: None for an open episode (the >=15% drawdown is still unrecovered
    #: at the series tail).
    recovery_date: str | None
    recovery_value: float | None


def find_episodes(
    values: Sequence[float],
    dates: Sequence[str],
    threshold: float = THRESHOLD,
) -> list[Episode]:
    """The qualifying drawdown episodes of a growth index, in date order.

    ``values`` is the index (base 1.0 in the seed month) and ``dates``
    its zero-padded ``YYYY.MM`` labels, same length, at least 2 rows.
    The seed month is the initial running peak. An episode opens the
    first month the index falls strictly below the running peak (the
    epsilon guards float noise), tracks the worst trough through
    sub-peaks that never reach a new high, and closes at the first month
    the index reaches the peak again (a new high advances the running
    peak). An episode qualifies when its worst trough depth
    ``1 - trough/peak`` is >= ``threshold`` inclusive; a qualifying open
    episode at the tail is returned with empty recovery fields.
    """
    if len(values) != len(dates):
        raise ValueError("values and dates must have the same length")
    if len(values) < 2:
        raise ValueError("an episode walk needs at least two rows")

    eps = EPS
    episodes: list[Episode] = []
    peak_i = 0
    peak_v = float(values[0])
    underwater = False
    trough_i = 0
    trough_v = peak_v

    def close(recovery_i: int | None) -> None:
        depth = 1.0 - trough_v / peak_v
        if depth >= threshold - eps:
            episodes.append(
                Episode(
                    depth=depth,
                    peak_date=str(dates[peak_i]),
                    peak_value=peak_v,
                    trough_date=str(dates[trough_i]),
                    trough_value=trough_v,
                    recovery_date=(
                        str(dates[recovery_i]) if recovery_i is not None else None
                    ),
                    recovery_value=(
                        float(values[recovery_i]) if recovery_i is not None else None
                    ),
                )
            )

    for i in range(1, len(values)):
        v = float(values[i])
        if not underwater:
            if v < peak_v - eps:
                underwater = True
                trough_i, trough_v = i, v
            else:  # a new high: the running peak advances
                peak_i, peak_v = i, v
        else:
            if v < trough_v - eps:
                trough_i, trough_v = i, v
            if v >= peak_v - eps:  # new high: the stretch closes here
                close(i)
                underwater = False
                peak_i, peak_v = i, v
    if underwater:
        close(None)
    return episodes


def serialize_csv(episodes: list[Episode]) -> bytes:
    """Pinned CSV serialization: repr() floats, empty recovery cells for
    open episodes, LF, final newline."""
    lines = [
        (
            "peak_date,peak_value,trough_date,trough_value,"
            "recovery_date,recovery_value,depth"
        )
    ]
    for ep in episodes:
        rec_d = ep.recovery_date if ep.recovery_date is not None else ""
        rec_v = repr(ep.recovery_value) if ep.recovery_value is not None else ""
        lines.append(
            f"{ep.peak_date},{ep.peak_value!r},{ep.trough_date},{ep.trough_value!r},"
            f"{rec_d},{rec_v},{ep.depth!r}"
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


def serialize_meta(episodes: list[Episode], vintage: dict) -> bytes:
    """Pinned sidecar serialization: json.dumps(indent=2, sort_keys=True) + newline.

    The ``vintage`` block is copied verbatim from the source series
    sidecar (one Vintage stamps the whole tree); ``episodes`` records
    the threshold, the epsilon, and the algorithm itself.
    """
    meta: dict[str, object] = {
        "name": NAME,
        "version": 1,
        "owner": OWNER,
        "units": {
            "peak_value": (
                "growth index, decimal (real monthly-rebalanced 60/40; "
                "base 1.0 at 1871.01)"
            ),
            "trough_value": (
                "growth index, decimal (worst month of the episode; "
                "same base as peak_value)"
            ),
            "recovery_value": (
                "growth index, decimal (first month at or above the "
                "peak; same base; empty for an open episode)"
            ),
            "depth": "decimal fraction of the peak lost at the worst trough "
            "(1 - trough/peak); 0.15 = a 15% drawdown",
        },
        "index": "YYYY.MM",
        "shape_family": "long-table",
        "serialization": (
            "csv: utf-8, LF newlines, final newline, values via Python repr(); "
            "open episodes leave the recovery cells empty; "
            "sidecar json: json.dumps(obj, indent=2, sort_keys=True) "
            "+ trailing newline"
        ),
        "vintage": vintage,
        "episodes": {
            "threshold": THRESHOLD,
            "epsilon": EPS,
            "algorithm": (
                "peak-to-new-high underwater stretches over the real "
                "monthly growth index: the seed month is the initial "
                "running peak; an episode opens when the index falls "
                "strictly below the running peak (float noise guarded "
                "by the epsilon) and closes at the first month the index "
                "reaches the peak again; an episode qualifies when its "
                "worst trough depth (1 - trough/peak) is >= 0.15 "
                "inclusive; a qualifying episode still open at the "
                "series tail keeps empty recovery fields"
            ),
            "count": len(episodes),
        },
        "row_count": len(episodes),
    }
    return (json.dumps(meta, indent=2, sort_keys=True) + "\n").encode("utf-8")


def build_episodes(root: Path) -> int:
    """Build the episodes artifacts under ``root/artifacts/metrics/``.

    Reads the committed canonical monthly series CSV (the ``real``
    column is the growth index) and its sidecar (the vintage stamp),
    computes the episodes, and writes the CSV + sidecar. Returns 0 on
    success; on a missing/malformed source or a write failure prints the
    named error to stderr and returns 1.
    """
    try:
        series_path = root / "artifacts" / "series" / SOURCE_CSV_NAME
        meta_path = root / "artifacts" / "series" / SOURCE_META_NAME
        if not series_path.is_file():
            raise FileNotFoundError(
                f"missing source artifact {SOURCE_CSV_NAME} (run the series "
                "stage first)"
            )
        if not meta_path.is_file():
            raise FileNotFoundError(
                f"missing source sidecar {SOURCE_META_NAME} (run the series "
                "stage first)"
            )
        source_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        vintage = source_meta.get("vintage")
        if not isinstance(vintage, dict):
            raise TypeError(
                f"source sidecar {SOURCE_META_NAME} carries no vintage dict "
                "(run the series stage first)"
            )

        lines = series_path.read_text(encoding="utf-8").split("\n")
        header, *rows = lines
        if header.strip() != "date,real,nominal":
            raise ValueError(
                f"unexpected source CSV header {header!r} in {SOURCE_CSV_NAME}"
            )
        rows = [row for row in rows if row]
        dates: list[str] = []
        values: list[float] = []
        for row in rows:
            parts = row.split(",")
            if len(parts) != 3:
                raise ValueError(f"malformed source CSV row: {row!r}")
            dates.append(parts[0])
            values.append(float(parts[1]))

        episodes = find_episodes(values, dates)
        out_dir = root.joinpath(*ARTIFACT_DIR)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / CSV_NAME).write_bytes(serialize_csv(episodes))
        (out_dir / META_NAME).write_bytes(serialize_meta(episodes, vintage))
    except (OSError, ValueError, KeyError) as exc:
        print(f"metrics: {exc}", file=sys.stderr)
        return 1
    print(
        f"metrics: {CSV_NAME} + {META_NAME} ({len(episodes)} episode(s) "
        f">= {THRESHOLD:g} over the real monthly index, {dates[0]} -> {dates[-1]})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(build_episodes(Path(__file__).resolve().parents[2]))
