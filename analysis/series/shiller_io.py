"""Vintage reader for the Shiller ``ie_data.xls`` dataset.

Sole xlrd I/O choke point for the whole study: every consumer of the
dataset reads it through this module. It enforces the pinned vintage
(sha256), slices the documented data rows, normalizes blank/``"NA"``
cells to ``None``, parses the ``YYYY.MM`` decimal date axis with
``month = round((dt - year) * 100)`` -- never float-arithmetic on the
fraction -- and exposes the free-text notes row (last sheet row).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import xlrd

#: Pinned vintage (ledger entry 2026-09-22, data/RUNLOG.md; DATA.md §1.1).
VINTAGE_SHA256 = "044196dafe44c3030b2facbdea023975b3f6aa68b4e52f8f9bafc403e19589c1"

#: Workbook-relative location of the dataset inside a repo checkout.
XLS_RELPATH = ("data", "ie_data.xls")

#: Data-sheet geometry pinned to the current file layout (DATA.md §1):
#: header row is 0-indexed 7; data rows start at 8 and the last row is a
#: free-text notes row, so data rows are 8 .. nrows-2 inclusive.
DATA_SHEET = "Data"
DATA_START_ROW = 8


class VintageError(Exception):
    """Raised when the dataset is missing or fails the sha256 pin."""


def _cell(value: object) -> float | None:
    """Map one cell to float | None ('' / 'NA' -> None, case-insensitive)."""
    if isinstance(value, str):
        s = value.strip()
        if s == "" or s.upper() == "NA":
            return None
        return float(s)
    if isinstance(value, (int, float)):
        return float(value)
    raise ValueError(f"unsupported cell type: {type(value).__name__}: {value!r}")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class Vintage:
    """Typed read of the construction columns of one pinned vintage.

    ``dates`` are parsed ``(year, month)`` tuples; every column list is
    the same length, aligned row-for-row, with ``None`` for blank cells.
    ``k`` is the re-basing constant K = last CPI in the file (DATA.md §4).
    """

    sha256: str
    last_row: tuple[int, int]
    k: float
    dates: tuple[tuple[int, int], ...]
    P: tuple[float | None, ...]  # col 1
    D: tuple[float | None, ...]  # col 2
    RT: tuple[float | None, ...]  # col 9
    CPI: tuple[float | None, ...]  # col 4
    BM: tuple[float | None, ...]  # col 17
    BR: tuple[float | None, ...]  # col 18
    notes_row: str  # last sheet row (nrows-1), non-blank segments joined with " / "


def load_vintage(root: Path, pin: str | None = VINTAGE_SHA256) -> Vintage:
    """Read and pin-check the dataset at ``root/data/ie_data.xls``.

    Raises :class:`VintageError` (naming the re-pull procedure, or the
    expected/actual sha256) before any sheet data is consumed.
    ``pin=None`` skips the sha256 check -- the pin-optional facts path
    used only by the vintage ledger recorder
    (``analysis/vintage_ledger.py``); the default stays strict.
    """
    path = root.joinpath(*XLS_RELPATH)
    if not path.is_file():
        raise VintageError(
            f"missing dataset {path}; re-pull it per the procedure in "
            f"data/RUNLOG.md (shillerdata.com CDN; do not use the stale Yale mirror)"
        )
    actual = _sha256(path)
    if pin is not None and actual != pin:
        raise VintageError(f"vintage sha256 mismatch: expected {pin}, got {actual}")

    wb = xlrd.open_workbook(str(path))
    sheet = wb.sheet_by_name(DATA_SHEET)
    nrows = sheet.nrows
    # Data rows: 0-indexed 8 .. nrows-2 (row 7 = header, last row = notes).
    rows = range(DATA_START_ROW, nrows - 1)

    dates: list[tuple[int, int]] = []
    cols: list[list[float | None]] = [[] for _ in range(6)]
    for r in rows:
        raw = sheet.row_values(r)
        dt = float(raw[0])
        year = int(dt)
        month = round((dt - year) * 100)
        if not 1 <= month <= 12:
            raise VintageError(f"unparsable date {dt!r} at data row {r}")
        dates.append((year, month))
        for out, idx in zip(cols, (1, 2, 9, 4, 17, 18)):
            out.append(_cell(raw[idx]))

    if not dates:
        raise VintageError("data sheet has no data rows")
    k_cells = [c for c in cols[3] if c is not None]
    if not k_cells:
        raise VintageError("no CPI values found (column 4)")
    # The last sheet row is a free-text notes row, not a data row.
    notes_segments = [
        str(value).strip()
        for value in sheet.row_values(nrows - 1)
        if str(value).strip()
    ]
    return Vintage(
        sha256=actual,
        last_row=dates[-1],
        k=k_cells[-1],
        dates=tuple(dates),
        P=tuple(cols[0]),
        D=tuple(cols[1]),
        RT=tuple(cols[2]),
        CPI=tuple(cols[3]),
        BM=tuple(cols[4]),
        BR=tuple(cols[5]),
        notes_row=" / ".join(notes_segments),
    )
