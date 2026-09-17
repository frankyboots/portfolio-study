#!/usr/bin/env python3
"""Probe pre-1926 D/E interpolation quality (DATA.md §9 item 6).

Quantify how "interpolated from annual data" the early D and E columns really
are: constant-run lengths, change cadence per year, value granularity, and
what the resulting D/P, E/P (and RealTR dividend yield) look like for
1871-1925, to decide whether 1871-1925 is usable for 60/40 return math.
"""
from collections import Counter
from pathlib import Path

import xlrd

wb = xlrd.open_workbook(str(Path(__file__).resolve().parent.parent / "data" / "ie_data.xls"))
d = wb.sheet_by_name("Data")
rows = [d.row_values(r) for r in range(8, d.nrows - 1)]  # data rows 8-1876; notes row excluded


def f(v):
    """Cell → float or None (blank / 'NA')."""
    if isinstance(v, str) and v.strip() in ("", "NA"):
        return None
    assert v is not None
    return float(v)


dates = [f(r[0]) for r in rows]
P = [f(r[1]) for r in rows]
D = [f(r[2]) for r in rows]
E = [f(r[3]) for r in rows]
CPI = [f(r[4]) for r in rows]


def ym(dt):
    y = int(dt)
    return y, round((dt - y) * 100)


pre: list[int] = []
for i, dt in enumerate(dates):
    assert dt is not None  # date column is complete
    if dt < 1926.0:
        pre.append(i)
print(f"pre-1926 rows: {len(pre)}  {ym(dates[pre[0]])} .. {ym(dates[pre[-1]])}")
for name, s in (("D", D), ("E", E)):
    # verify completeness in window
    missing = [i for i in pre if s[i] is None]
    assert not missing, f"{name} has blanks pre-1926 at {missing}"

for name, s in (("D", D), ("E", E)):
    vals = [s[i] for i in pre]
    assert all(v is not None for v in vals)
    vals = [v for v in vals if v is not None]
    runs = []
    cur = 1
    for i in range(1, len(vals)):
        if vals[i] == vals[i - 1]:
            cur += 1
        else:
            runs.append(cur)
            cur = 1
    runs.append(cur)
    hist = Counter(runs)
    print(f"\n=== {name} 1871-1925 ===")
    print(f"  distinct values: {len(set(vals))}")
    print(f"  run-length hist (len:count): " + ", ".join(f"{k}:{v}" for k, v in sorted(hist.items())[:15]))
    print(f"  max run: {max(runs)} months; months inside runs of >=12: {sum(c for l, c in hist.items() if l >= 12)}/{len(vals)}")
    # where does each year's values change?
    chg_years = Counter()
    for a, b in zip(pre[:-1], pre[1:]):
        assert s[a] is not None and s[b] is not None
        if s[b] != s[a]:
            chg_years[ym(dates[b])[0]] += 1
    per_year = [chg_years[y] for y in range(1871, 1926)]
    print(f"  changes/year: min={min(per_year)} max={max(per_year)} | years with >=10 changes: {sum(1 for v in per_year if v >= 10)}/55")
    # which months carry the changes?
    months = Counter(ym(dates[b])[1] for a, b in zip(pre[:-1], pre[1:]) if s[b] != s[a])
    print(f"  change months: {dict(sorted(months.items()))}")
    # granularity: how many distinct values
    print(f"  distinct value sample: {sorted(set(vals))[:8]} ... {sorted(set(vals))[-4:]}")
    # value jumps at change points (absolute)
    jumps = [abs(s[b] - s[a]) for a, b in zip(pre[:-1], pre[1:]) if s[b] != s[a]]
    if jumps:
        print(f"  jump size: min={min(jumps):.4f} max={max(jumps):.4f} median={sorted(jumps)[len(jumps)//2]:.4f}")

# D/P and E/P in pre-1926 vs post-1926 (annual read, per §9 item 5)
print("\n=== implied D/P, E/P (annual read) pre- vs post-1926 ===")
for label, idxs in (("1871-1925", pre), ("1926-1990", [i for i, dt in enumerate(dates) if 1926.0 <= dt < 1990.0])):
    dps_, eps_ = [], []
    for i in idxs:
        assert dates[i] is not None
        if D[i] is not None and P[i]:
            dps_.append(D[i] / P[i] * 100)
        if E[i] is not None and P[i]:
            eps_.append(E[i] / P[i] * 100)
    print(f"  {label}: D/P {min(dps_):.2f}..{max(dps_):.2f}% (med {sorted(dps_)[len(dps_)//2]:.2f}) | E/P {min(eps_):.2f}..{max(eps_):.2f}% (med {sorted(eps_)[len(eps_)//2]:.2f})")

# flat-year examples for D
print("\n=== sample: D values 1871-1885 (every 6th month) ===")
for i in pre[:180:6]:
    y, m = ym(dates[i])
    print(f"  {y}.{m:02d} D={D[i]}  E={E[i]}  P={P[i]}")

# how many years have D constant ALL year
print("\n=== years where D is constant all 12 months ===")
const_years = []
for y in range(1871, 1926):
    vals = [D[i] for i in pre if ym(dates[i])[0] == y]
    if len(set(vals)) == 1:
        const_years.append(y)
print(f"  {len(const_years)}/55 years: {const_years}")

# same for E
const_years_e = []
for y in range(1871, 1926):
    vals = [E[i] for i in pre if ym(dates[i])[0] == y]
    if len(set(vals)) == 1:
        const_years_e.append(y)
print(f"  E: {len(const_years_e)}/55 years: {const_years_e}")
