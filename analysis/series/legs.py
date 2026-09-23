"""Shared 60/40 leg engine: the one owner of the construction conventions.

Both builders -- the monthly-rebalanced canonical series
(:mod:`canonical_60_40`) and the calendar-year-end-rebalanced comparator
(:mod:`rebalance_comparator`) -- must consume their per-month leg
factors from this module, so the divergence between the two rebalancing
conventions is attributable to the rebalancing rule alone, never to a
second construction of the legs.

This module owns:

- the content-driven endpoint walk (trailing provisional records);
- the mid-series ``None`` guard (a blank required input inside the used
  range is a build failure, not a provisional exclusion);
- the BM-shift vs ``BR*CPI`` identity cross-check at rel-tol 1e-12
  (guards both the one-month lead and the read; DATA.md §8);
- the per-month leg factors ``(g_eq_real, g_bond_real, g_eq_nom,
  g_bond_nom)`` with their zero-padded ``YYYY.MM`` labels.

Leg conventions (all verified in data/DATA.md):

- Real legs: equity = RealTR growth (col 9); bond = BR growth (col 18).
- Nominal legs: equity month factor = ``(P + D/12) / P_prev``; bond
  month factor = col 17 (BM) shifted down one row -- month ``i`` uses
  ``BM[i-1]``.
- The endpoint is the last month where every construction input (P, D,
  CPI, BR; ``BM[i-1]`` for nominal bonds) is present; trailing months
  with blank required inputs are excluded and recorded with reasons.
"""

from __future__ import annotations

from dataclasses import dataclass

from .shiller_io import Vintage

#: Rel tolerance for the BM-shift vs BR*CPI identity cross-check
#: (the suite's BM-identity tolerance; DATA.md §8).
BM_IDENTITY_REL_TOL = 1e-12

#: The one pinned data-quality note (DATA.md §7) carried verbatim by
#: every sidecar under artifacts/series/ -- shared by the monthly and
#: the annual-rebalance comparator serializers so they cannot drift.
DATA_QUALITY_NOTES: tuple[str, ...] = (
    (
        "DATA.md §7: the 2025.10 CPI value is Shiller's fill-in; BLS never "
        "released October 2025 CPI (2025 lapse in appropriations). 2026.08 "
        "and 2026.09 CPI values are Shiller estimates."
    ),
)


class BuildError(Exception):
    """Raised on a construction-convention failure (gap, identity, tail)."""


def label(ym: tuple[int, int]) -> str:
    """Zero-padded YYYY.MM label from a parsed (year, month) pair."""
    return f"{ym[0]}.{ym[1]:02d}"


@dataclass(frozen=True)
class LegMonth:
    """The shared leg factors for one return month (month ``i > 0``)."""

    label: str
    month: int  # 1..12; the calendar month the factors belong to
    g_eq_real: float  # RT[i] / RT[i-1]
    g_bond_real: float  # BR[i] / BR[i-1]
    g_eq_nom: float  # (P[i] + D[i]/12) / P[i-1]
    g_bond_nom: float  # BM[i-1] (cross-checked against BR*CPI)


@dataclass(frozen=True)
class LegSet:
    """The construction range of one Vintage, as shared leg factors.

    ``end_index`` is the last used data-row index (the content-driven
    endpoint); ``seed_label`` is the zero-padded YYYY.MM label of data
    row 0 (the seed month, which carries no return factor); ``excluded``
    records the trailing provisional months with reasons. ``months``
    holds one :class:`LegMonth` per return month -- data rows
    ``1..end_index``, in file order, so ``months[0]`` is the return
    month immediately after the seed -- and every :class:`LegMonth`
    carries its own zero-padded ``YYYY.MM`` label, calendar month
    (1..12), and the four per-month leg factors.
    """

    end_index: int
    seed_label: str
    excluded: tuple[tuple[str, str], ...]
    months: tuple[LegMonth, ...]


def _take(col: tuple[float | None, ...], i: int, name: str, lbl: str) -> float:
    """Return the non-None value at ``i``, else fail naming month and column.

    The pre-loop mid-series guard already guarantees presence for P/D/CPI/
    BR/BM inside the used range; this keeps the factor loop total and
    gives RT (not part of the content-driven endpoint rule) the same
    named failure.
    """
    value = col[i]
    if value is None:
        raise BuildError(f"mid-series gap at {lbl}: column '{name}' is blank")
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


def build_legs(v: Vintage) -> LegSet:
    """Build the shared leg factors for one Vintage.

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
            (label(v.dates[j]), f"required input(s) missing: {', '.join(missing)}")
        )
        j -= 1
    if _month_inputs_ok(v, j):
        raise BuildError(
            f"seed month {label(v.dates[0])} lacks required inputs: "
            f"{', '.join(_month_inputs_ok(v, 0))}"
        )
    excluded.reverse()

    # Mid-series guard: any None inside [0..j] is a build failure, not
    # a provisional exclusion.
    for i in range(j + 1):
        for name, col in (("P", v.P), ("D", v.D), ("CPI", v.CPI), ("BR", v.BR)):
            if col[i] is None:
                raise BuildError(
                    f"mid-series gap at {label(v.dates[i])}: column '{name}' is blank"
                )
        if i > 0 and v.BM[i - 1] is None:
            raise BuildError(
                f"mid-series gap at {label(v.dates[i])}: column 'BM (nominal bond factor, shifted)' is blank"
            )

    months: list[LegMonth] = []
    for i in range(1, j + 1):
        lab = label(v.dates[i])
        prev = label(v.dates[i - 1])
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

        months.append(
            LegMonth(
                label=lab,
                month=v.dates[i][1],
                g_eq_real=rt_i / rt_prev,
                g_bond_real=br_i / br_prev,
                g_eq_nom=(p_i + d_i / 12) / p_prev,
                g_bond_nom=bm_prev,
            )
        )

    return LegSet(
        end_index=j,
        seed_label=label(v.dates[0]),
        excluded=tuple(excluded),
        months=tuple(months),
    )
