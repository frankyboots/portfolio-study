# _archive — original ad-hoc probes (superseded)

These scripts were the exploratory probes that produced DATA.md. They are
archived (not deleted) because several contain useful diagnostic output, but
they are **not** maintained:

- **Superseded by `../validate_data_md.py`** — a single end-to-end regression
  suite covering every quantitative claim in DATA.md (81 checks, exit code
  1 on failure). Run that instead of hunting through the probes.
- Several have bugs. Anything you read below or in DATA.md that was
  derived from a buggy output has been re-verified independently; the
  archive is kept only for historical reference.

Known bugs per file (found during 2026-09-17 validation):

| file | bug |
|---|---|
| `probe2.py` | `ym()` parses month as `round(frac*12)` instead of `round(frac*100)` → false "1712 gaps / 1557 duplicates"; column stats include the notes row (P "min 2.73 / max 7711.32" are contaminated) |
| `probe3.py` | test [4] uses **P** (nominal) as the CAPE numerator → reports 1746 violations. The correct RealPrice variant is in `probe4.py` and passes with 0 violations |
| `probe5.py` | crashes at the last print block: `BM[1868]` is None |
| `probe8.py` | crashes in the recovered-price correlation block |
| `probe_final.py` | Fraction check has a malformed formula → always prints `0/1869` (actual: 1869/1869); BM min/max print `nan@2026.09` |
| `probe_last.py` | crashes at line 31: array length mismatch in `np.corrcoef` |
| `probe13.py` | tail-CAPE "mystery" (stored 40.5758 vs 40.4566) came from using nominal P with a same-month 117-window; the stored value **exactly** equals `RealPrice/mean(118 available RealE, prior-month window)` |
| `probe9.py` / `probe10.py` / `probe12.py` | **BM misalignment artifact (resolved 2026-09-17, see DATA.md §8):** computed BM's implied duration / BM-vs-BR correlation against the *same-month* GS10 change `GS[i]−GS[i−1]`. BM is actually the *next month's* nominal factor — `BM[i] = (BR[i+1]/BR[i])·(CPI[i+1]/CPI[i])` exactly — so the "erratic post-1952 duration" and "corr ≈ 0.27 / 1981.11 moving opposite" findings were the one-month offset, not a data anomaly. Redo any BM vs GS10 comparison against `GS[i+1]−GS[i]`. |
| `probe_pre1926.py` | clean (2026-09-17): quantified the pre-1926 D/E interpolation for §9 item 6 (RESOLVED — linear within-year ramps, not piecewise-constant); its claims are now regression checks in `../validate_data_md.py` |

Clean / historically consistent: probe1, probe4, probe6, probe7, probe11 (probe3 is clean except test [4]; probe9/10/12 are misaligned — see table above).

Note: `probe13.py` used `wb.author` / `wb.last_saved_time`, attributes that
xlrd 1.x had but **xlrd 2.x removed** — under the current venv (xlrd 2.0.2)
it will crash at line 4. For OLE metadata use `olefile` (see
`../validate_data_md.py`).
