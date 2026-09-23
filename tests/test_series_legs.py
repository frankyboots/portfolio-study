"""The two build_legs BuildError branches with no XLS dependency.

``tests/test_series_canonical.py`` carries a module-level skip mark
when the raw .xls is absent (not committed: no license on the source
site), so the synthetic-Vintage error-branch tests live here in an
XLS-independent file calling ``legs.build_legs`` directly.

Covered branches:

- one data row -> "need at least two data rows";
- the provisional-tail walk-back exhausts to row 0 and row 0 still
  lacks required inputs -> "seed month ... lacks required inputs".
"""

from __future__ import annotations

import pytest

from analysis.series import legs
from analysis.series.shiller_io import Vintage


def _vintage(**overrides: object) -> Vintage:
    """A two-row synthetic Vintage with every required input present."""
    base: dict = {
        "sha256": "0" * 64,
        "last_row": (1871, 2),
        "k": 333.8925,
        "dates": ((1871, 1), (1871, 2)),
        "P": (100.0, 101.0),
        "D": (1.2, 1.3),
        "RT": (4.0, 4.1),
        "CPI": (40.0, 40.5),
        "BM": (1.0, 1.0),
        "BR": (0.04, 0.04),
        "notes_row": "test",
    }
    base.update(overrides)
    return Vintage(**base)


def test_build_legs_needs_at_least_two_data_rows() -> None:
    one_row = _vintage(
        last_row=(1871, 1),
        dates=((1871, 1),),
        P=(100.0,),
        D=(1.2,),
        RT=(4.0,),
        CPI=(40.0,),
        BM=(1.0,),
        BR=(0.04,),
    )
    with pytest.raises(legs.BuildError, match="need at least two data rows"):
        legs.build_legs(one_row)


def test_build_legs_seed_month_lacks_required_inputs() -> None:
    # D blank at BOTH rows: the content-driven endpoint walk-back
    # exhausts the provisional tail to row 0, and the seed month itself
    # still lacks a required input -- the seed BuildError branch, not
    # the mid-series gap branch (row 1 is excluded, not guarded).
    seed_missing = _vintage(D=(None, None))
    with pytest.raises(
        legs.BuildError, match=r"seed month 1871\.01 lacks required inputs"
    ):
        legs.build_legs(seed_missing)
