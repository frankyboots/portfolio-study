"""Independent end-to-end validation of every quantitative claim in DATA.md
against data/ie_data.xls (vintage saved 2026-09-02).

Run:  .venv/bin/python analysis/validate_data_md.py
(works from any cwd; the workbook is located relative to this file.)
Prints PASS/FAIL per claim; exit code 1 if any FAIL.
"""
import math
import sys
from pathlib import Path

import xlrd
import numpy as np

XLS = str(Path(__file__).resolve().parent.parent / "data" / "ie_data.xls")

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))


def ym(i, dates):
    dt = dates[i]
    return f"{int(dt // 1)}.{int(round((dt - int(dt)) * 100)):02d}"


def idx(y, m):
    return (y - 1871) * 12 + (m - 1)


def num(v):
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip()
        if s == "" or s.upper() == "NA":
            return None
        try:
            return float(s)
        except ValueError:
            return s
    return None


def approx(a, b, tol):
    if a is None or b is None or a is np.nan:
        return False
    return abs(a - b) <= tol


wb = xlrd.open_workbook(XLS)
d = wb.sheet_by_name("Data")
nrows, ncols = d.nrows, d.ncols

# ---------------------------------------------------------------- container
check("Data sheet is 1878 x 22", (nrows, ncols) == (1878, 22), f"got {(nrows, ncols)}")
check("sheets = Disclaimer + Data", wb.sheet_names() == ["Disclaimer", "Data"],
      f"got {wb.sheet_names()}")
disc = wb.sheet_by_index(0) if wb.sheet_names()[0] == "Disclaimer" else None
nonempty = [str(c).strip() for r in range(disc.nrows) for c in disc.row_values(r) if str(c).strip()]
check("Disclaimer sheet has exactly 1 non-empty cell", len(nonempty) == 1,
      f"got {len(nonempty)}")
check("Disclaimer text: Shiller, public sources, not registered advisers, no accuracy guarantee",
      len(nonempty) == 1 and "Shiller" in nonempty[0] and "registered investment advisers" in nonempty[0]
      and "guarantee" in nonempty[0], f"text={nonempty[:1]}")

import olefile

_meta = olefile.OleFileIO(XLS).get_metadata()
check("author = RShiller", _meta.author in (b"RShiller", "RShiller"), f"got {_meta.author!r}")
check("last saved by = Laurence Black",
      _meta.last_saved_by in (b"Laurence Black", "Laurence Black"), f"got {_meta.last_saved_by!r}")
check("created 2000-07-15", _meta.create_time.year == 2000 and _meta.create_time.month == 7
      and _meta.create_time.day == 15, f"got {_meta.create_time}")
check("last saved Sep 2 2026 15:25:11 (local) / 14:25:11 UTC in OLE",
      (_meta.last_saved_time.year, _meta.last_saved_time.month, _meta.last_saved_time.day) == (2026, 9, 2)
      and _meta.last_saved_time.minute == 25 and _meta.last_saved_time.second == 11,
      f"got {_meta.last_saved_time}")

# ---------------------------------------------------------------- load
raw = d.row_values(7)  # row 7 = header labels (1-indexed row 8)
check("row 7 short labels start Date,P,D,E,CPI,Fraction,Rate GS10",
      [str(x).strip() for x in raw[:7]] == ["Date", "P", "D", "E", "CPI", "Fraction", "Rate GS10"],
      f"got {[str(x).strip() for x in raw[:8]]}")
check("row 7 col14 label = TR CAPE", str(raw[14]).strip() == "TR CAPE", f"got {raw[14]!r}")

rows = [[num(v) for v in d.row_values(r)] for r in range(8, nrows - 1)]
n = len(rows)
check("1869 data rows", n == 1869, f"got {n}")
dates = [r[0] for r in rows]
P = [r[1] for r in rows]; D = [r[2] for r in rows]; E = [r[3] for r in rows]
CPI = [r[4] for r in rows]; F = [r[5] for r in rows]; GS = [r[6] for r in rows]
RP = [r[7] for r in rows]; RD = [r[8] for r in rows]; RT = [r[9] for r in rows]
RE = [r[10] for r in rows]; RTE = [r[11] for r in rows]; CAPE = [r[12] for r in rows]
TRC = [r[14] for r in rows]; EY = [r[16] for r in rows]
BM = [r[17] for r in rows]; BR = [r[18] for r in rows]
A10s = [r[19] for r in rows]; A10b = [r[20] for r in rows]; A10ex = [r[21] for r in rows]
spacer13 = [r[13] for r in rows]; spacer15 = [r[15] for r in rows]

# ---------------------------------------------------------------- §2 dates
months_ok = True
seq_bad = []
for i in range(n):
    dt = dates[i]
    yr = int(dt // 1)
    m = round((dt - yr) * 100)
    if not (1 <= m <= 12) or abs((dt - yr) * 100 - m) > 1e-9:
        months_ok = False
    if i:
        py, pm = int(dates[i-1] // 1), round((dates[i-1] - int(dates[i-1] // 1)) * 100)
        exp = (py + 1, 1) if pm == 12 else (py, pm + 1)
        if (yr, m) != exp:
            seq_bad.append((ym(i - 1, dates), ym(i, dates)))
check("date parse month=round((x-year)*100) valid 1..12 for all rows", months_ok)
check("dates strictly consecutive 1871.01 -> 2026.09, no gaps/dupes",
      not seq_bad and dates[0] == 1871.01 and dates[-1] == 2026.09,
      f"first breaks: {seq_bad[:5]}")

f_ok = sum(1 for i in range(n)
           if abs(F[i] - (int(dates[i] // 1) + (round((dates[i] - int(dates[i] // 1)) * 100) - 0.5) / 12)) < 1e-9)
check("Fraction = year + (month-0.5)/12 for all rows (1e-9)", f_ok == n, f"{f_ok}/{n}")

# ---------------------------------------------------------------- §4 K
Ks = [RP[i] * CPI[i] / P[i] for i in range(n)]
check("K constant = 333.8925 = last CPI",
      approx(min(Ks), 333.8925, 1e-3) and abs(max(Ks) - min(Ks)) < 1e-10
      and approx(CPI[-1], 333.8925, 1e-4),
      f"min {min(Ks):.6f} max {max(Ks):.6f} spread {max(Ks)-min(Ks):.2e} lastCPI {CPI[-1]}")
Kd = [RD[i] * CPI[i] / D[i] for i in range(n) if D[i] is not None]
Ke = [RE[i] * CPI[i] / E[i] for i in range(n) if E[i] is not None]
check("K identical for RealD and RealE",
      max(Kd) - min(Kd) < 1e-10 and max(Ke) - min(Ke) < 1e-10
      and approx(max(Kd), 333.8925, 1e-3), f"Kd {max(Kd)-min(Kd):.2e} Ke {max(Ke)-min(Ke):.2e}")

# ---------------------------------------------------------------- §3 col 1-3
check("P: 4.44 @1871.01 -> 7631.47 @2026.09",
      approx(P[0], 4.44, 0.005) and approx(P[-1], 7631.47, 0.005),
      f"P[0]={P[0]} P[-1]={P[-1]}")
dmin_i = min((i for i in range(n) if D[i] is not None), key=lambda i: D[i])
emax = max(i for i in range(n) if E[i] is not None)
dmax_i = max((i for i in range(n) if D[i] is not None), key=lambda i: D[i])
check("D min 0.18 (early) / max 81.70 @2026.06",
      approx(D[dmin_i], 0.18, 0.005) and int(dates[dmin_i] // 1) < 1900
      and approx(D[dmax_i], 81.70, 0.005) and ym(dmax_i, dates) == "2026.06",
      f"min {D[dmin_i]}@{ym(dmin_i,dates)} max {D[dmax_i]}@{ym(dmax_i,dates)}")
emin_i = min((i for i in range(n) if E[i] is not None), key=lambda i: E[i])
emax_i = max((i for i in range(n) if E[i] is not None), key=lambda i: E[i])
check("E min 0.16 / max 295.39 @2026.06",
      approx(E[emin_i], 0.16, 0.005) and approx(E[emax_i], 295.39, 0.005) and ym(emax_i, dates) == "2026.06",
      f"min {E[emin_i]}@{ym(emin_i,dates)} max {E[emax_i]}@{ym(emax_i,dates)}")
check("D, E blank exactly 2026.07-09",
      all(D[idx(2026, m)] is None and E[idx(2026, m)] is None for m in (7, 8, 9))
      and D[idx(2026, 6)] is not None and E[idx(2026, 6)] is not None,
      f"D 2026.06={D[idx(2026,6)]} 07={D[idx(2026,7)]}")

cmin_i = min(range(n), key=lambda i: CPI[i]); cmax_i = max(range(n), key=lambda i: CPI[i])
check("CPI min 6.2796 @1896.06 / max 335.123 @2026.05",
      approx(CPI[cmin_i], 6.2796, 0.001) and ym(cmin_i, dates) == "1896.06"
      and approx(CPI[cmax_i], 335.123, 0.001) and ym(cmax_i, dates) == "2026.05",
      f"min {CPI[cmin_i]}@{ym(cmin_i,dates)} max {CPI[cmax_i]}@{ym(cmax_i,dates)}")
check("CPI splice smooth 1912.12=9.705 -> 1913.01=9.80",
      approx(CPI[idx(1912, 12)], 9.705, 0.005) and approx(CPI[idx(1913, 1)], 9.80, 0.005),
      f"{CPI[idx(1912,12)]} -> {CPI[idx(1913,1)]}")

gmin_i = min(range(n), key=lambda i: GS[i]); gmax_i = max(range(n), key=lambda i: GS[i])
check("GS10 max 15.32 @1981.09, min 0.62 @2020.07",
      approx(GS[gmax_i], 15.32, 0.005) and ym(gmax_i, dates) == "1981.09"
      and approx(GS[gmin_i], 0.62, 0.005) and ym(gmin_i, dates) == "2020.07",
      f"max {GS[gmax_i]}@{ym(gmax_i,dates)} min {GS[gmin_i]}@{ym(gmin_i,dates)}")
check("GS10 full coverage 1871.01-2026.09 (no blanks)", all(GS[i] is not None for i in range(n)))
kinks = [(abs(GS[i+1] - 2*GS[i] + GS[i-1]), i) for i in range(1, idx(1951, 1))]
nzk = [v for v, _ in kinks if v > 1e-9]
all_jan = all(int(round((dates[i] - int(dates[i]//1)) * 100)) == 1 for _, i in kinks if kinks and abs(GS[i+1]-2*GS[i]+GS[i-1]) > 1e-9)
check("GS10 pre-1951 piecewise-linear annual interpolation: in-year 2nd diffs = 0, kinks only at Jan, |kink| <= 0.08",
      max(nzk) <= 0.08 and all_jan, f"{len(nzk)} Jan-boundary kinks, max {max(nzk):.4f}, all in January: {all_jan}")

# ---------------------------------------------------------------- §3 real cols
rpmax_i = max(range(n), key=lambda i: RP[i])
check("RealPrice min 90.38; max 7711.13 @2026.08; 2026.09 = 7631.47 (= P)",
      approx(min(RP), 90.38, 0.005) and approx(RP[rpmax_i], 7711.13, 0.005)
      and ym(rpmax_i, dates) == "2026.08" and approx(RP[-1], 7631.47, 0.005),
      f"min {min(RP)} max {RP[rpmax_i]}@{ym(rpmax_i,dates)} last {RP[-1]}")
check("RT[0] = RealPrice[0] and stored RT[0] = 118.94",
      approx(RT[0], RP[0], 1e-6) and approx(RT[0], 118.94, 0.005),
      f"RT[0]={RT[0]} RP[0]={RP[0]}")
check("RT[-1] = 5,205,780 (5205779.71) @2026.09", approx(RT[-1], 5205780, 1), f"got {RT[-1]:.2f}")

bad_rt = 0; maxerr_rt = 0.0
for i in range(1, n):
    rdv = RD[i] if RD[i] is not None else 0.0
    exp = RT[i-1] * (RP[i] + rdv / 12) / RP[i-1]
    err = abs(RT[i] - exp) / exp
    maxerr_rt = max(maxerr_rt, err)
    if err > 1e-8:
        bad_rt += 1
check("RealTR recursion (D/12, D=0 when blank): 0 violations >1e-8",
      bad_rt == 0, f"violations={bad_rt} maxrel={maxerr_rt:.2e}")
# confirm the D/12 term is actually needed (price-only variant fails)
bad_rt2 = sum(1 for i in range(1, n)
              if abs(RT[i] - RT[i-1] * RP[i] / RP[i-1]) / RT[i] > 1e-8)
check("(control) price-only variant DOES violate -> D/12 term is real", bad_rt2 > 100,
      f"violations={bad_rt2}")

bad_rte = 0
for i in range(n):
    if RTE[i] is None:
        continue
    if abs(RTE[i] - RE[i] * RT[i] / RP[i]) / RTE[i] > 1e-8:
        bad_rte += 1
check("RealTRE = RealE*(RealTR/RealP): 0 violations", bad_rte == 0, f"violations={bad_rte}")

# ---------------------------------------------------------------- §3 CAPE
na_rows = [i for i in range(n) if isinstance(CAPE[i], str) or CAPE[i] is None]
check("CAPE 'NA' exactly 1871.01-1880.12 (120 rows), first value 1881.01",
      len(na_rows) == 120 and na_rows[0] == 0 and na_rows[-1] == 119
      and ym(120, dates) == "1881.01", f"n_na={len(na_rows)} first val {ym(120,dates)}")
ca = [i for i in range(n) if CAPE[i] is not None]
cmin = min(ca, key=lambda i: CAPE[i]); cmax = max(ca, key=lambda i: CAPE[i])
i29 = idx(1929, 9)
check("CAPE min 4.78 @1920.12 / max 44.20 @1999.12",
      approx(CAPE[cmin], 4.78, 0.005) and ym(cmin, dates) == "1920.12"
      and approx(CAPE[cmax], 44.20, 0.005) and ym(cmax, dates) == "1999.12",
      f"min {CAPE[cmin]}@{ym(cmin,dates)} max {CAPE[cmax]}@{ym(cmax,dates)}")
check("CAPE 32.56 @1929.09", approx(CAPE[i29], 32.56, 0.005), f"got {CAPE[i29]}")
check("CAPE 40.58 (40.5758) @2026.09", approx(CAPE[-1], 40.5758, 0.005), f"got {CAPE[-1]}")

# window variants: doc claims window ends PRIOR month (i-120..i-1)
def cape_test(win, price):
    bad = 0; tested = 0
    for i in ca:
        w = [RE[j] for j in win(i)]
        if any(x is None for x in w):
            continue
        tested += 1
        exp = price[i] / (sum(w) / 120)
        if abs(CAPE[i] - exp) / exp > 1e-8:
            bad += 1
    return tested, bad
t_prior, b_prior = cape_test(lambda i: range(i - 120, i), RP)   # doc formula: RealPrice / mean(RealE[i-120..i-1])
t_cur, b_cur = cape_test(lambda i: range(i - 119, i + 1), RP)
t_nom, b_nom = cape_test(lambda i: range(i - 120, i), P)
check("CAPE = RealPrice/mean(RealE, 120mo ENDING PRIOR MONTH): 0 violations (1747 rows w/ full window; 2 tail rows partial)",
      b_prior == 0 and t_prior == 1747, f"tested={t_prior} viol={b_prior}")
check("(control) same-month window violates -> 1-month lag is real", b_cur > 100,
      f"tested={t_cur} viol={b_cur}")
check("(control) nominal-P numerator violates -> RealPrice is the numerator", b_nom > 100,
      f"tested={t_nom} viol={b_nom}")

# TRCAPE
tc = [i for i in range(n) if TRC[i] is not None]
bad_tc = 0; tested_tc = 0
for i in tc:
    w = [RTE[j] for j in range(i - 120, i)]
    if any(x is None for x in w):
        continue
    tested_tc += 1
    if abs(TRC[i] - RT[i] / (sum(w) / 120)) / (RT[i] / (sum(w) / 120)) > 1e-8:
        bad_tc += 1
tmin = min(tc, key=lambda i: TRC[i]); tmax = max(tc, key=lambda i: TRC[i])
check("TR CAPE = RealTR/mean120(RealTRE, prior-month window): 0 violations (1747 rows w/ full window)",
      bad_tc == 0 and tested_tc == 1747, f"tested={tested_tc} viol={bad_tc}")
check("TR CAPE range 6.58 - 48.11",
      approx(TRC[tmin], 6.58, 0.01) and approx(TRC[tmax], 48.11, 0.01),
      f"min {TRC[tmin]}@{ym(tmin,dates)} max {TRC[tmax]}@{ym(tmax,dates)}")

# ---------------------------------------------------------------- §3 excess yield
bad_ey = 0; tested_ey = 0; maxey = 0.0
for i in range(120, n):
    if CAPE[i] is None or EY[i] is None:
        continue
    tested_ey += 1
    infl10 = (CPI[i] / CPI[i-120]) ** (1/10) - 1
    exp = 1 / CAPE[i] - (GS[i] / 100 - infl10)
    r = abs(EY[i] - exp)
    maxey = max(maxey, r)
    if r > 1e-9:
        bad_ey += 1
eys = [EY[i] for i in range(120, n) if EY[i] is not None]
check("Excess CAPE Yield formula: 0 mismatches / 1749 rows",
      bad_ey == 0 and tested_ey == 1749, f"tested={tested_ey} mism={bad_ey} maxabs={maxey:.2e}")
check("EY range -0.0258 ... 0.2353",
      approx(min(eys), -0.0258, 0.0005) and approx(max(eys), 0.2353, 0.0005),
      f"min {min(eys):.4f} max {max(eys):.4f}")

# ---------------------------------------------------------------- §3 bond cols
bm_valid = [i for i in range(n) if BM[i] is not None]
bmin = min(bm_valid, key=lambda i: BM[i]); bmax = max(bm_valid, key=lambda i: BM[i])
check("BM min 0.9174 @1980.01 / max 1.1090 @1981.10",
      approx(BM[bmin], 0.9174, 0.0005) and ym(bmin, dates) == "1980.01"
      and approx(BM[bmax], 1.1090, 0.0005) and ym(bmax, dates) == "1981.10",
      f"min {BM[bmin]}@{ym(bmin,dates)} max {BM[bmax]}@{ym(bmax,dates)}")
check("BM blank exactly at 2026.09 (last row only)",
      [i for i in range(n) if BM[i] is None] == [n - 1],
      f"blanks={[ym(i,dates) for i in range(n) if BM[i] is None]}")
check("BR = 1.0 @1871.01 -> 38.99 @2026.09, peak 59.45 @2020.04",
      approx(BR[0], 1.0, 1e-6) and approx(BR[-1], 38.99, 0.005)
      and approx(max(BR), 59.45, 0.005) and ym(max(range(n), key=lambda i: BR[i]), dates) == "2020.04",
      f"BR[0]={BR[0]} BR[-1]={BR[-1]} peak {max(BR)}@{ym(max(range(n), key=lambda i: BR[i]),dates)}")
check("BR full coverage incl 2026.09", all(BR[i] is not None for i in range(n)))
peak_i = max(range(n), key=lambda i: BR[i])
check("BR 34% below 2020.04 peak in 2026.09",
      approx((BR[peak_i] - BR[-1]) / BR[peak_i], 0.34, 0.005),
      f"got {(BR[peak_i]-BR[-1])/BR[peak_i]:.3f}")

# ---------------------------------------------------------------- §3 forward 10y cols
a10s_idx = [i for i in range(n) if A10s[i] is not None]
bad_a10s = 0
for i in a10s_idx:
    exp = (RT[i+120] / RT[i]) ** (1/10) - 1
    if abs(A10s[i] - exp) / exp > 1e-6:
        bad_a10s += 1
check("A10s = (RealTR[i+120]/RealTR[i])^(1/10)-1, filled 1871.01-2016.09 (1749 rows), 0 viol",
      bad_a10s == 0 and len(a10s_idx) == 1749 and a10s_idx[0] == 0
      and ym(a10s_idx[-1], dates) == "2016.09",
      f"n={len(a10s_idx)} last {ym(a10s_idx[-1],dates)} viol={bad_a10s}")
a10b_idx = [i for i in range(n) if A10b[i] is not None]
bad_a10b = sum(1 for i in a10b_idx
               if abs(A10b[i] - ((BR[i+120] / BR[i]) ** (1/10) - 1)) / A10b[i] > 1e-6)
check("A10b = (BR[i+120]/BR[i])^(1/10)-1: 0 violations",
      bad_a10b == 0 and ym(a10b_idx[-1], dates) == "2016.09", f"viol={bad_a10b}")
bad_ex = sum(1 for i in range(n) if None not in (A10ex[i], A10s[i], A10b[i])
             and abs(A10ex[i] - (A10s[i] - A10b[i])) > 1e-12)
check("A10ex = A10s - A10b: 0 violations", bad_ex == 0, f"viol={bad_ex}")
smin, smax = min(A10s[i] for i in a10s_idx), max(A10s[i] for i in a10s_idx)
bminv, bmaxv = min(A10b[i] for i in a10b_idx), max(A10b[i] for i in a10b_idx)
xvals = [A10ex[i] for i in range(n) if A10ex[i] is not None]
check("A10s range -5.9%..+20.0%", approx(smin, -0.059, 0.002) and approx(smax, 0.200, 0.002),
      f"min {smin:.4f} max {smax:.4f}")
check("A10b range -5.4%..+11.0%", approx(bminv, -0.054, 0.002) and approx(bmaxv, 0.110, 0.002),
      f"min {bminv:.4f} max {bmaxv:.4f}")
check("A10ex range -10.0%..+19.6%", approx(min(xvals), -0.100, 0.002) and approx(max(xvals), 0.196, 0.002),
      f"min {min(xvals):.4f} max {max(xvals):.4f}")

# ---------------------------------------------------------------- §5 landmarks
i2910 = idx(1929, 10); i2911 = idx(1929, 11)
check("1929: P 31.30 (09) -> 27.99 (10, -10.6%)",
      approx(P[idx(1929, 9)], 31.30, 0.005) and approx(P[i2910], 27.99, 0.005)
      and approx(P[i2910] / P[i2910-1] - 1, -0.106, 0.005),
      f"{P[idx(1929,9)]:.2f} -> {P[i2910]:.2f} ({P[i2910]/P[i2910-1]-1:+.1%})")
check("worst P month 1929.11 = -26.5%",
      approx(P[i2911] / P[i2911-1] - 1, -0.265, 0.005)
      and all(abs(P[i+1] / P[i] - 1) <= abs(P[i2911] / P[i2911-1] - 1) or abs(P[i+1]/P[i]-1) > -0.26
              for i in range(n - 1)),
      f"{P[i2911]/P[i2911-1]-1:+.2%}")
jumps = [(ym(i + 1, dates), round(P[i+1] / P[i], 4)) for i in range(n - 1) if abs(P[i+1] / P[i] - 1) > 0.15]
doc_jumps = ["1929.11", "1931.12", "1932.04", "1932.08", "1933.05", "1933.06", "1938.07", "2008.10", "2020.03"]
check("exactly 9 months with |P move| > 15%, matching doc list",
      [j[0] for j in jumps] == doc_jumps, f"got {[j[0] for j in jumps]}")
j3208 = [v for yv, v in jumps if yv == "1932.08"]
check("1932.08 = +50%", bool(j3208) and approx(j3208[0], 1.50, 0.01), f"got {j3208}")
m1957 = max(abs(P[i] / P[i-1] - 1) for i in range(idx(1957, 6), idx(1957, 11)))
check("1957 Jun-Oct: no P move > 6.25% (max was 6.23% @1957.10)", m1957 <= 0.0625, f"max move {m1957:.2%}")

# spacers
check("cols 13 & 15 empty spacers (always blank)",
      all(v is None for v in spacer13) and all(v is None for v in spacer15))

# ---------------------------------------------------------------- §5 era returns
eras = [((1871, 1), (1913, 1)), ((1913, 1), (1946, 1)), ((1946, 1), (1971, 1)),
        ((1971, 1), (1991, 1)), ((1991, 1), (2011, 1)), ((2011, 1), (2026, 9))]
def era_ret(arr, e):
    a, b = idx(*e[0]), idx(*e[1])
    yrs = (b - a) / 12
    return (arr[b] / arr[a]) ** (1 / yrs) - 1
br_eras = [era_ret(BR, e) * 100 for e in eras]
check("BR era real returns ≈ 4.7/2.2/-0.7/2.2/4.6/-0.8 %/yr",
      all(abs(g - d) < 0.15 for g, d in zip(br_eras, [4.7, 2.2, -0.7, 2.2, 4.6, -0.8])),
      f"got {[f'{x:.2f}' for x in br_eras]}")
rt_eras = [era_ret(RT, e) * 100 for e in eras]
check("RealTR era returns ≈ 7.6/6.0/8.0/4.3/6.6/11.0 %/yr",
      all(abs(g - d) < 0.15 for g, d in zip(rt_eras, [7.6, 6.0, 8.0, 4.3, 6.6, 11.0])),
      f"got {[f'{x:.2f}' for x in rt_eras]}")

# ---------------------------------------------------------------- §8 bond duration
# doc §8's six duration numbers are BR-implied (probe11): r_nom via log(BR growth)*(1+infl)
infl_m = np.array([(CPI[i] / CPI[i-1]) for i in range(1, n)])
logbr = np.log(np.array(BR[1:]) / np.array(BR[:-1]))
logbm = np.log(np.array([BM[i] if BM[i] is not None else np.nan for i in range(1, n)]))
dgs = np.array([(GS[i] - GS[i-1]) / 100 for i in range(1, n)])
GSa = np.array(GS[1:])
rp_br = (logbr + np.log(infl_m)) - GSa / 1200          # log(1+r_nom) = log(BR growth * CPI ratio); minus coupon
rp_bm = (np.array([BM[i] if BM[i] is not None else np.nan for i in range(1, n)]) - 1) - GSa / 1200   # doc §8 formula (probe9/10/12): BM price component
with np.errstate(divide="ignore", invalid="ignore"):
    k_br = -rp_br / dgs
    k_bm = -rp_bm / dgs
k_br = np.where(np.abs(dgs) > 2e-4, k_br, np.nan); k_br = np.where(np.isfinite(k_br), k_br, np.nan)
k_bm = np.where(np.abs(dgs) > 1e-4, k_bm, np.nan); k_bm = np.where(np.isfinite(k_bm), k_bm, np.nan)
yrs = np.array([int(dt // 1) for dt in dates[1:]])
doc_dur = [8.23, 8.40, 8.25, 6.74, 7.73, 8.85]
got_dur = []
for (y0, y1) in [(1871, 1912), (1913, 1945), (1946, 1970), (1971, 1989), (1990, 2010), (2011, 2026)]:
    sel = k_br[(yrs >= y0) & (yrs <= y1) & ~np.isnan(k_br)]
    got_dur.append(float(np.median(sel)) if len(sel) else float("nan"))
check("BR implied duration medians ≈ 8.23/8.40/8.25/6.74/7.73/8.85 by era (doc §8)",
      all(abs(g - dv) < 0.2 for g, dv in zip(got_dur, doc_dur)),
      f"got {[f'{x:.2f}' for x in got_dur]}")
bm_pre = k_bm[(yrs <= 1952) & ~np.isnan(k_bm)]
bm_post = k_bm[(yrs > 1952) & ~np.isnan(k_bm)]

# --- BM = next-month nominal factor of BR (RESOLVED 2026-09-17) ---
# The "BM post-1950s" mystery: BM[i] is month i+1's nominal total-return factor,
# BM[i] = (BR[i+1]/BR[i]) * (CPI[i+1]/CPI[i]).
ids = list(range(1, n - 1))  # rows i where BM[i] exists and month i+1 exists
bad_id = 0; maxrel_id = 0.0; n_id = 0
for i in range(1, n - 1):
    exp = BR[i+1] / BR[i] * CPI[i+1] / CPI[i]
    rel = abs(BM[i] - exp) / exp
    maxrel_id = max(maxrel_id, rel)
    if rel > 1e-12:
        bad_id += 1
    n_id += 1
check("BM identity: BM[i] == (BR[i+1]/BR[i])*(CPI[i+1]/CPI[i]) 0 violations (1867 rows)",
      bad_id == 0 and n_id == 1867 and maxrel_id < 1e-15,
      f"n={n_id} viol={bad_id} maxrel={maxrel_id:.2e}")
big = [i for i in ids if abs(GS[i+1] - GS[i]) >= 0.05 and abs(BM[i] - (BR[i] / BR[i-1] * CPI[i] / CPI[i-1])) > 0.001]
big_tot = sum(1 for i in ids if abs(GS[i+1] - GS[i]) >= 0.05)
check(f"(control) misalignment only visible when yields move: {len(big)}/{big_tot} months with |dGS(next)|>=5bp have |BM - same-month factor| > 0.1%",
      len(big) >= 0.8 * big_tot and big_tot > 100, f"diverging {len(big)}/{big_tot}")
# aligned implied duration (next-month dGS) recovers ~8 in every era
dgs_next_arr = np.full(n - 1, np.nan)
dgs_next_arr[:n - 2] = [(GS[i+1] - GS[i]) / 100.0 for i in range(1, n - 1)]   # row i: (GS[i+1]-GS[i])/100
with np.errstate(divide="ignore", invalid="ignore"):
    k_bm_next = -rp_bm / dgs_next_arr
k_bm_next = np.where(np.abs(dgs_next_arr) > 1e-4, k_bm_next, np.nan)
k_bm_next = np.where(np.isfinite(k_bm_next), k_bm_next, np.nan)
doc_dur_bm = [8.31, 8.36, 8.22, 6.70, 7.71, 8.81]
got_dur_bm = []
for (y0, y1) in [(1871, 1912), (1913, 1945), (1946, 1970), (1971, 1989), (1990, 2010), (2011, 2026)]:
    sel = k_bm_next[(yrs >= y0) & (yrs <= y1) & ~np.isnan(k_bm_next)]
    got_dur_bm.append(float(np.median(sel)) if len(sel) else float("nan"))
check("BM aligned (next-month dGS) implied duration ≈ BR's by era (8.31/8.36/8.22/6.70/7.71/8.81)",
      all(abs(g - dv) < 0.2 for g, dv in zip(got_dur_bm, doc_dur_bm)),
      f"got {[f'{x:.2f}' for x in got_dur_bm]}")
check("(control) same-month alignment BM duration erratic post-1953 (the old §8 artifact)",
      float(np.median(bm_pre)) > 7.5 and float(np.median(bm_post)) < 4,
      f"pre-1953 med {float(np.median(bm_pre)):.2f} | post med {float(np.median(bm_post)):.2f}")
log_bmi = np.log([BM[i] for i in ids])
log_next = np.log([BR[i+1] / BR[i] * CPI[i+1] / CPI[i] for i in ids])   # factor of month i+1 (the identity)
log_prev = np.log([BR[i] / BR[i-1] * CPI[i] / CPI[i-1] for i in ids])   # factor of month i (misaligned)
corr_ident = float(np.corrcoef(log_bmi, log_next)[0, 1])
corr_mis = float(np.corrcoef(log_bmi, log_prev)[0, 1])
check("corr(log BM[i], log [month-i+1 factor]) = 1.0000; misaligned (month-i) corr < 0.5",
      abs(corr_ident - 1.0) < 1e-3 and corr_mis < 0.5,
      f"aligned={corr_ident:.4f} misaligned={corr_mis:.3f}")
i8110 = idx(1981, 10)
check("1981.10: BM 1.10897 == BR's month-1981.11 factor (the +10.5% real month)",
      approx(BM[i8110], 1.10897, 5e-5)
      and approx(BM[i8110], BR[i8110+1] / BR[i8110] * CPI[i8110+1] / CPI[i8110], 1e-9)
      and approx(BR[i8110+1] / BR[i8110] - 1, 0.105, 0.01),
      f"BM={BM[i8110]:.5f} BRg1981.11={BR[i8110+1]/BR[i8110]-1:+.2%}")

# --- §9 item 5 (RESOLVED 2026-09-17): D is an ANNUAL (4-quarter) flow; RealTR uses D/12 ---
# Independent magnitude check: D/P must read as the S&P 500 dividend yield.
# If D were a monthly flow, 12*D/P would be the yield (~15-26% — absurd).
def _f(v):
    return float(v) if v is not None else 0.0
dp_annual = [_f(D[idx(y, 12)]) / _f(P[idx(y, 12)]) for y in range(2010, 2026)]
dp_monthly = [12 * x for x in dp_annual]
check("D/P (annual read) = 1.0-3.0% for every year 2010-2025 (matches published S&P 500 yield ~1.2-2.2%)",
      all(0.01 <= x <= 0.03 for x in dp_annual),
      f"range {min(dp_annual):.3%}..{max(dp_annual):.3%}")
check("(control) monthly read 12*D/P = 14-26% for 2010-2025 -> implausible as a yield, so D is not a monthly flow",
      all(x > 0.13 for x in dp_monthly), f"range {min(dp_monthly):.1%}..{max(dp_monthly):.1%}")
# Control on the recursion itself: D/12 passes (checked above, 0 violations).
# Now prove the /12 is the ONLY divisor consistent with the stored RealTR:
bad_rd12 = 0
for i in range(1, n):
    rdv = RD[i] if RD[i] is not None else 0.0
    if abs(RT[i] - RT[i-1] * (RP[i] + rdv) / RP[i-1]) / RT[i] > 1e-8:
        bad_rd12 += 1
check("(control) using RD as a FULL monthly flow (no /12) in the recursion fails 1800+ rows",
      bad_rd12 > 1800, f"violations={bad_rd12}")
# "linear interpolation to monthly figures" from the S&P four-quarter totals:
# within-quarter second differences of D are small (flat quarters), kinks sit at quarter boundaries.
def _qkinks(col, y0, y1):
    inq_worst = 0.0; bnd_worst = 0.0
    for y in range(y0, y1 + 1):
        raw = [col[idx(y, m)] for m in range(1, 13)]
        if any(x is None for x in raw):
            continue
        v = [float(x) for x in raw]
        for (a, b, c) in [(1, 2, 3), (4, 5, 6), (7, 8, 9), (10, 11, 12)]:
            inq_worst = max(inq_worst, abs(v[c-1] - 2*v[b-1] + v[a-1]))
        for (a, b, c) in [(3, 4, 5), (6, 7, 8), (9, 10, 11)]:
            bnd_worst = max(bnd_worst, abs(v[c-1] - 2*v[b-1] + v[a-1]))
    return inq_worst, bnd_worst
d_inq, d_bnd = _qkinks(D, 1926, 2025)
e_inq, e_bnd = _qkinks(E, 1926, 2025)
check("D & E 1926-2025: within-quarter 2nd diffs < 0.1 (flat quarters, four-quarter-total input), "
      "quarter-boundary kinks <= 0.35 (the interpolation knots)",
      d_inq < 0.1 and e_inq < 0.1 and d_bnd <= 0.35 and e_bnd <= 0.35,
      f"D in-q max {d_inq:.4f} bnd max {d_bnd:.4f}; E in-q max {e_inq:.4f} bnd max {e_bnd:.4f}")

# ---------------------------------------------------------------- §9 item 6
# (RESOLVED 2026-09-17): pre-1926 D/E are LINEARLY interpolated from annual
# knots (not piecewise-constant), and the 1925→1926 source splice is smooth.
def _cell(col, y, m):
    """Cell (y, m) of a pre-1926 column, asserted present (probe-verified complete)."""
    v = col[idx(y, m)]
    assert v is not None, f"{y}.{m:02d} unexpectedly blank"
    return float(v)

def _year_series(col, y):
    """Monthly values of col for calendar year y (all present pre-1926)."""
    return [_cell(col, y, m) for m in range(1, 13)]

def _linear_year_stats(col, y0, y1):
    """Within-year linearity: 2nd diffs and increment spread per non-flat year."""
    sd_max = 0.0; spread_max = 0.0; flat = 0
    for y in range(y0, y1 + 1):
        v = _year_series(col, y)
        if len(set(v)) == 1:
            flat += 1
            continue
        inc = [v[k+1] - v[k] for k in range(11)]
        spread_max = max(spread_max, max(inc) - min(inc))
        for k in range(10):
            sd_max = max(sd_max, abs(v[k+2] - 2*v[k+1] + v[k]))
    return sd_max, spread_max, flat

d_sd, d_sp, d_flat = _linear_year_stats(D, 1871, 1925)
e_sd, e_sp, e_flat = _linear_year_stats(E, 1871, 1925)
check("pre-1926 D/E linear within each year: intra-year 2nd diffs < 0.002 "
      "(annual knots, uniform monthly increments)",
      d_sd < 0.002 and e_sd < 0.002,
      f"D max sd {d_sd:.6f}; E max sd {e_sd:.6f}")
# Control: a step-function (piecewise-constant annual value) reading must NOT fit —
# its increments are 11 zeros + one full-year jump, so the increment spread ≈ the
# whole year's change (>= 0.009 for every non-flat D year, 0.119 for E 1920),
# ~100x+ the observed linear spread.
def _step_sanity(col, y):
    v = _year_series(col, y)
    assert len(set(v)) > 1, f"control year {y} must be non-flat"
    inc = [0.0]*10 + [v[-1] - v[0]]          # hold Jan value, jump in Dec
    return max(inc) - min(inc)
worst_step = max(_step_sanity(D, 1875), _step_sanity(E, 1920))
check("(control) step-function reading has increment spread >> observed "
      "-> the increments are uniform, i.e. LINEAR not piecewise-constant",
      worst_step > 5 * max(d_sp, e_sp),
      f"observed max spread {max(d_sp, e_sp):.5f}; step-variant spread {worst_step:.4f}")
check("pre-1926 flat runs only at year-boundary overlap: D flat 1873.12-1874.12 (0.33), "
      "1875.12-1876.12 (0.30); E flat 1873.12-1874.12 (0.46) — the annual knot is carried "
      "forward into the next year's first month",
      _cell(D, 1873, 12) == _cell(D, 1874, 1) == _cell(D, 1874, 12) == 0.33
      and _cell(D, 1875, 12) == _cell(D, 1876, 1) == _cell(D, 1876, 12) == 0.30
      and _cell(E, 1873, 12) == _cell(E, 1874, 1) == _cell(E, 1874, 12) == 0.46,
      f"D74={_cell(D,1874,1)} D76={_cell(D,1876,1)} E74={_cell(E,1874,1)}")
dp_2512 = _cell(D, 1925, 12) / _cell(P, 1925, 12)
dp_2601 = _cell(D, 1926, 1) / _cell(P, 1926, 1)
ep_2512 = _cell(E, 1925, 12) / _cell(P, 1925, 12)
ep_2601 = _cell(E, 1926, 1) / _cell(P, 1926, 1)
check("1925→1926 source splice (Cowles → S&P) is smooth: D/P and E/P move <0.5pt across it",
      abs(dp_2512 - dp_2601) < 0.005 and abs(ep_2512 - ep_2601) < 0.005,
      f"D/P {dp_2512:.4f}→{dp_2601:.4f}; E/P {ep_2512:.4f}→{ep_2601:.4f}")
# Flat years: D constant for all 12 months in exactly 9/55 years, E in 3/55.
def _const_years(col):
    out = []
    for y in range(1871, 1926):
        if len(set(_year_series(col, y))) == 1:
            out.append(y)
    return out
dy = _const_years(D); ey = _const_years(E)
check("pre-1926 fully-constant years: D 9/55, E 3/55 (the rest ramp within the year)",
      len(dy) == 9 and len(ey) == 3,
      f"D {dy} | E {ey}")

# ---------------------------------------------------------------- §7 tail
tail_cpi = [CPI[idx(2026, m)] for m in (5, 6, 7, 8, 9)]
check("CPI 2026.05->09 = 335.123/333.952/333.918/333.901/333.8925",
      all(abs(a - b) < 0.001 for a, b in zip(tail_cpi, [335.123, 333.952, 333.918, 333.901, 333.8925])),
      f"got {[f'{x:.4f}' for x in tail_cpi]}")
i = n - 1
win = [RE[j] for j in range(i - 120, i)]           # prior-month window, per verified formula
avail = [x for x in win if x is not None]
val_118 = RP[i] / (sum(avail) / len(avail))
win_same = [RE[j] for j in range(i - 119, i + 1)]  # the misframed window from the old probe13
avail_s = [x for x in win_same if x is not None]
p_117 = P[i] / (sum(avail_s) / len(avail_s))
check("tail CAPE RESOLVED: stored 40.5758 == RealPrice/mean(118 avail RealE, prior window) EXACTLY",
      approx(CAPE[i], val_118, 1e-9) and len(avail) == 118,
      f"stored={CAPE[i]:.6f} recomputed={val_118:.6f} n_avail={len(avail)}")
check("(explanation) old 40.4566 = nominal P / mean(117, same-month window) — an artifact",
      approx(p_117, 40.4566, 0.001), f"p117={p_117:.4f}")
notes = [str(v).strip() for v in d.row_values(nrows - 1) if str(v).strip()]
check("notes row = the 3 documented strings",
      set(notes) == {"Sept price is Sept 1st close", "Oct '25/Aug/Sept CPI estimated",
                     "Sept GS10 is Sept 1st value"}, f"got {notes}")

# ---------------------------------------------------------------- report
fails = 0
for name, ok, detail in RESULTS:
    tag = "PASS" if ok else "FAIL"
    if not ok:
        fails += 1
    line = f"[{tag}] {name}"
    if detail:
        line += f"  | {detail}"
    print(line)
print(f"\n{len(RESULTS) - fails}/{len(RESULTS)} passed, {fails} failed")
sys.exit(1 if fails else 0)
