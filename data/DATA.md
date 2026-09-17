# DATA.md — `ie_data.xls` (Shiller IE dataset), fully mapped

> Purpose: data spike — ground truth for what this dataset contains, to carry into the 150-year 60/40 study (real + nominal). It documents the data; construction and design decisions (e.g. the canonical 60/40 build) belong to project planning, not this document.
> Everything below was verified **empirically against the exact file** at
> `./data/ie_data.xls` (probes in `analysis/`), or against Shiller's published
> descriptions (shillerdata.com). Verified formulas are marked ✅ (0 violations
> across all applicable rows). All open questions in §9 are resolved (2026-09-17);
> it is kept as the record of what the spike settled.

---

## 1. Provenance & file container

- **What**: "Stock Market Data Used in *Irrational Exuberance*" — Princeton UP 2000, 2005, 2015, updated. Robert J. Shiller.
- **Container**: legacy BIFF `.xls` (Composite Document). Sheets: `Disclaimer` (1 cell), `Data` (1878 × 22).
- **File metadata**: author `RShiller`, last saved by `Laurence Black`, created 2000-07-15, **last saved Wed Sep 2 15:25:11 2026**.
- **Update cadence**: monthly, around the **1st of the month** (see §7 provisional tail). Download fresh each session; the file moves under you (CPI base, last month, notes all change).
- **Header layout**: rows 1–6 = merged multi-line title band, **row 7 = short column labels** (`Date, P, D, E, CPI, Fraction, Rate GS10, …`), rows 8–1876 = data (1869 months), **row 1877 = free-text notes row** (see §7).
- **Disclaimer sheet** (verbatim): data and CAPE developed by Shiller using various public sources; not investment advice; no guarantee of accuracy.
- **Licensing**: none stated. shillerdata.com carries a disclaimer (warranty disavowal + authorship statement for Robert J. Shiller, RSBB-I, LLC) but **no license grant**. Treated as free-for-research (public distribution since 2000, stable Yale mirror, no ToS); the `.xls` itself is therefore **not committed** to this repo — pull it per the recipe below and pin the vintage in the run log instead.

### 1.1 Provenance pin (verified copy of this dataset vintage)

| | |
|---|---|
| Source | <https://shillerdata.com/> (link is a CDN blob with rotating `?ver=` — scrape the page for the current href). **As of 2026-09-17 this CDN blob IS the current file** (sha256 `044196da…89c1`, `?ver=` = Sep 2 2026 17:52 UTC). |
| Mirror | ⚠️ `http://www.econ.yale.edu/~shiller/data/ie_data.xls` was **stale as of 2026-09-17**: `Last-Modified: Tue, 17 Oct 2023` (1,628,672 bytes, last row 2023.09, last-saved 2023-09-17, saved by "Bob S", notes row `"Aug/Sept CPI estimated"` — no `Oct '25`). Do NOT use the Yale URL as the primary source; scrape shillerdata.com. |
| Vintage | last saved **Wed Sep 2 15:25:11 2026**; last row **2026.09**; K (last CPI) **333.8925** |
| Hash | `sha256: 044196dafe44c3030b2facbdea023975b3f6aa68b4e52f8f9bafc403e19589c1` (1,674,752 bytes, 2026-09-17 pull) |

All quantitative claims in this file were validated against the pinned copy (`analysis/validate_data_md.py`, 81 checks, 2026-09-17). After each re-pull: record the new vintage (last-saved stamp, last row date, K) and re-run the suite.

## 2. Date axis — ✅ verified

- 1869 rows, **1871.01 → 2026.09**, **no gaps, no duplicates, strictly ordered**.
- **Date format is `YYYY.MM` decimal, NOT a year fraction.** `1871.1` = **October** 1871. Parse: `year = floor(x)`, `month = round((x − year)·100)`. Never float-arithmetic the month.
- **Prices are month-averages of daily closes** (Shiller's site) — **not** point-in-time month-end values. (Exception: the final, in-progress month uses the 1st-of-month close, §7.)
- `Fraction` col = `year + (month − 0.5)/12` — i.e. **mid-month** date fraction, for interpolation/continuous-time use.

## 3. Columns (all 22), with verified semantics

Columns 0–12 are the **documented, canonical 14-column dataset** (Shiller's site lists exactly these 14; third-party parsers strip the rest). Cols 13–21 are **undocumented extras** present in the current file (13, 15 are empty spacers; 16–21 are described below from reverse engineering).

| # | Label (row 7) | Meaning | Notes |
|---|---|---|---|
| 0 | Date | YYYY.MM decimal | §2 |
| 1 | P | S&P Composite **price** level (unadjusted, price-only) | monthly avg of daily closes. 4.44 (1871.01) → 7631.47 (2026.09). Pre-1926 reconstructed (Cowles); S&P history proper starts 1926. No reconstitution jumps >15% except real crash months (§5). |
| 2 | D | Dividend **$ amount** (not per-share yield) | **Annual (trailing four-quarter) total per share, spread across months** (§9 item 5, resolved). Since 1926: S&P 4-quarter totals linearly interpolated to monthly (Shiller). Pre-1926: Cowles, **linearly interpolated within each year from annual knots** (verified, §9 item 6 — not piecewise-constant). **Blank 2026.07–09** (not yet published at file save). Min 0.18 (early), max 81.70 (2026.06). RealTR uses **D/12** as the monthly cash dividend (verified). |
| 3 | E | Earnings **$ amount** (index EPS level) | Same sourcing as D. **Blank 2026.07–09.** Min 0.16, max 295.39 (2026.06). Updates monthly in recent years. |
| 4 | CPI | Consumer Price Index, **1982–84 = 100 basis** | CPI-U (BLS) from **Jan 1913**; **before 1913 spliced to Warren & Pearson price index** (`Gold and Prices`, 1935) scaled to CPI-U at Jan 1913 (Shiller's site). Splice is smooth: 1912.12 = 9.705 → 1913.01 = 9.80. 6.2796 (min, **1896.06**, pre-1913 W&P-spliced era) → 335.123 (max, 2026.05). **The file's CPI is the BLS unadjusted (NSA) CPI-U, exact to 3 decimals**: 2025.01→2026.07 matches FRED `CPIAUCNS` to 0.000 every month (2025.10 excluded — see §7, Oct 2025 never released). **Aug/Sep 2026 values in this vintage are ESTIMATES** (BLS releases post-date the file; §7). |
| 5 | Fraction | mid-month date fraction | §2 |
| 6 | Rate GS10 | 10-yr US long-term Treasury yield, **%, monthly** | Full coverage 1871.01→2026.09. Max **15.32% @ 1981.09**, min **0.62% @ 2020.07**. Early years are smooth (linearly-interpolated annual vintages); the GS10 column is a *yield*, and the bond-return columns are **not** reproducible from it (§8). Sep 2026 = Sept 1st value (notes row). |
| 7 | Real Price | ✅ `P · K / CPI`, **K = 333.8925 = last CPI in file** | See §4 for the critical re-basing quirk. Min 90.38 (1877.06); **max 7711.13 @ 2026.08**; 2026.09 = 7631.47 (= P, since K is the *last* CPI and P fell in Sept). |
| 8 | Real Dividend | ✅ `D · K / CPI` | Blank where D blank. |
| 9 | Real TR Price | ✅ recursion `RT[i] = RT[i-1]·(RealPrice[i] + RealDiv[i]/12)/RealPrice[i-1]`, `RT[0] = RealPrice[0]` | **Real total-return index**, seeded at 118.94 in 1871.01, = 5,205,780 in 2026.09. Dividends assumed **monthly = D/12** (D is the flowing amount, NOT a 12× level). Where D is blank (2026.07–09) the recursion used **D = 0** (verified 0 violations). This is the column to use for real equity total returns. |
| 10 | Real Earnings | ✅ `E · K / CPI` | Blank where E blank. |
| 11 | Real TR Scaled Earnings | ✅ `RealE[i] · (RealTR[i]/RealPrice[i])` | Earnings "scaled" into total-return price space (repurchase-adjustment mechanic per Bunn & Shiller 2014 / Jivraj & Shiller 2017). |
| 12 | CAPE | ✅ `RealPrice[i] / mean(RealE[i-120 … i-1])` | **Window = 120 months ENDING THE PREVIOUS MONTH** (1-month lag vs textbook). 'NA' string for 1871.01–1880.12 (120-month warmup). First value 1881.01. Min **4.78 @ 1920.12**, 32.56 @ 1929.09, max **44.20 @ 1999.12**, 40.58 @ 2026.09. Tail caveat §7. |
| 13 | — | empty spacer | always blank |
| 14 | TR CAPE | ✅ `RealTR[i] / mean(RealTRE[i-120 … i-1])` | Total-return CAPE (repurchase-bias-corrected). Same window rule, same warmup. 6.58 (min) → 48.11 (max). |
| 15 | — | empty spacer | always blank |
| 16 | Excess CAPE Yield | ✅ `1/CAPE[i] − (GS10[i]/100 − ((CPI[i]/CPI[i-120])^(1/10) − 1))` | Earnings yield minus **10-yr real Treasury yield** (nominal yield minus 10-yr geometric-annualized CPI inflation). 0 mismatches / 1749 rows. Range −0.0258 … 0.2353. |
| 17 | Monthly Total Bond Returns | ✅ `(BR[i+1]/BR[i])·(CPI[i+1]/CPI[i])` — **next month's** nominal 10-yr bond total-return factor, stored one row early | **One-month lead, see §8 (resolved).** Blank 2026.09 (no next month — *that* is why the last row is blank, not a missing value). Min 0.9174 @1980.01, max 1.1090 @1981.10. |
| 18 | Real Total Bond Returns | **cumulative REAL bond total-return index**, = 1.0 at 1871.01 → 38.99 @ 2026.09 (peak **59.45 @ 2020.04**) | See §8. Full coverage incl. 2026.09. |
| 19 | 10 Year Annualized Stock Real Return | ✅ `(RealTR[i+120]/RealTR[i])^(1/10) − 1` | ⚠️ **FORWARD** 10-yr realized return — **look-ahead data**. Filled 1871.01 → 2016.09 (exactly the rows with a full 120 future months). Range −5.9% … +20.0%. |
| 20 | 10 Year Annualized Bonds Real Return | ✅ `(BR[i+120]/BR[i])^(1/10) − 1` | Same look-ahead property. −5.4% … +11.0%. |
| 21 | Real 10 Year Excess Annualized Returns | ✅ `col19 − col20` | −10.0% … +19.6%. |

## 4. THE re-basing quirk (most important for reproducibility)

Every "Real" column (7–11) is deflated with a **constant K = 333.8925 = the CPI of the last row in the file** (verified: `RealP·CPI/P` = 333.8925 for all 1869 rows, spread 2e-13).

Consequences:
- All real levels are in **"latest-month dollars"** — here, Sep 2026 dollars.
- **Every monthly file release silently rescales the entire real history** by `CPI_new/CPI_old`. Real levels are only comparable *within one file vintage*.
- **Invariant across vintages**: ratios and returns (CAPE, TR CAPE, RealTR growth, BR growth, real excess returns). Do all long-run return math on ratios/growth, or pin one file and recompute real levels with a fixed CPI base if you want stable absolutes.
- Third-party corroboration (IAR wiki): "recomputing with a different CPI series will not match the stored values."

## 5. Integrity checks & history landmarks (verified in this file)

- ✅ All identities in §3 hold with **0 violations** (rel. tol 1e-8, except tail months noted in §7).
- **1929 crash present**: P 31.30 (1929.09) → 27.99 (1929.10, −10.6%); worst P month **1929.11 (−26.5%)**.
- Only |P monthly move| > 15%: 1929.11, 1931.12, 1932.04, 1932.08 (+50%), 1933.05, 1933.06, 1938.07, 2008.10, 2020.03 — i.e. real events, **no index-reconstitution jumps** visible in P.
- **1957** (S&P reconstitution to 500): no level jump in P (Jun–Oct 1957 moves ≤ 6.25%; max 6.23% @ 1957.10) — the price series is level-continuous.
- BR regime summary (real 10-yr bond, geometric annualized): 1871–1913 **+4.7%/yr** · 1913–1946 +2.2% · 1946–1971 **−0.7%** · 1971–1991 +2.2% · 1991–2011 +4.6% · 2011–2026 **−0.8%**. Real stocks (RealTR): 7.6 / 6.0 / 8.0 / 4.3 / 6.6 / 11.0 % per the same eras. **BR is 34% below its 2020.04 peak in 2026.09** — the real bond sleeve is mid-bear.

## 6. Source-data vintages (per Shiller's published notes)

- **P, D, E**: sources as in *Market Volatility* (MIT Press 1989) ch. 26.
  - **≥1926**: S&P four-quarter totals, linearly interpolated monthly.
  - **<1926**: Cowles & Associates, *Common Stock Indexes* (2nd ed., 1939), **linearly interpolated from annual data within each calendar year** (verified 2026-09-17, §9 item 6: uniform monthly increments, 9/55 fully-constant years for D). Pre-1926 monthly D/E are smoothed approximations, but the 1925→1926 source splice is smooth (D/P 4.82%→4.80%, E/P 10.03%→9.87%).
- **CPI**: BLS CPI-U from 1913; **pre-1913 = Warren & Pearson** price index spliced at Jan 1913.
- **GS10**: 10-yr long-term government bond rate (GS-sourced), from 1871.
- **TR CAPE**: added Sep 2018, per Bunn & Shiller (2014), Jivraj & Shiller (2017) — the repurchase/buyback correction.

## 7. The provisional tail (current file: saved 2026-09-02)

Notes row (verbatim): `Sept price is Sept 1st close` · `Oct '25/Aug/Sept CPI estimated` · `Sept GS10 is Sept 1st value`.

So in this vintage:
- **2026.09**: P and GS10 are **Sept 1st values** (not month-end). D, E, RealD, RealE, RealTRE **blank**. BM also blank — but for a structural reason, not a missing value: BM holds the *next month's* factor (§8), and there is no month after 2026.09.
- **2026.07–09**: D/E blank → **RealTR recursion used D=0** (dividends dropped) → 2026.07–09 total-return growth is slightly understated.
- **CPI estimates, exactly pinned down (2026-09-17, vs BLS/FRED — the note's three flagged months are exactly the problem months):**
  - The file's CPI column is the **BLS unadjusted (NSA) CPI-U, exact to 3 decimals**: 2025.01→2026.07 matches FRED `CPIAUCNS` to 0.000 every month (2025.10 excluded — never released, below).
  - **2026.07 = published actual** (BLS released July 2026 CPI on 2026-08-12, before this file's 2026-09-02 save): 333.918, exact match to FRED.
  - **2026.08 and 2026.09 = Shiller estimates** (BLS releases Aug 2026 CPI on 2026-09-11, *after* the save). Shiller's Aug estimate 333.901 is **~1.08 below** the actual 334.980 now in FRED (BLS Aug release: +0.4% SA); expect both to move in the next vintage.
  - **`Oct '25` is real, not stale template text**: BLS **never released October 2025 CPI** — 2025 government-shutdown lapse in appropriations ("The Oct 2025 data values are not available due to the 2025 lapse in appropriations" — BLS, July 2026 release; FRED has a gap at 2025.10; the Nov 2025 release reported a combined Sept–Nov change). Shiller's 2025.10 = 325.212 is **his own fill-in**, sitting *above* both neighboring actuals (Sep 324.800, Nov 324.122). The Yale 2023-vintage file (pre-shutdown, no such month) carries the older note `"Aug/Sept CPI estimated"` — the `Oct '25` term was added in later vintages.
- **The 2026.06 CPI drop is REAL, not an artifact** (was: "verify vs BLS"). 335.123 → 333.952 (−1.171 pts, **−0.349% NSA**) is the **steepest NSA monthly decline since 2015.12 (−0.342%) and the only NSA decline in the 89 months of 2019.01–2026.05**. BLS's July 2026 release confirms June **−0.4% SA**, driven by energy (gasoline −9.7% SA, energy −5.7% SA); 12-mo all-items through Jun 2026 = 3.4%. The "declining path" 335.123 → 333.8925 is thus real through 2026.07 and estimate-only for Aug/Sep.
- **CAPE 2026.08/09** are computed with **missing earnings in the window** (E ends 2026.06). Tail CAPEs are stale-ish by ~3 months of earnings. (The earlier "40.5758 vs 40.4566 mismatch" is **resolved**: the stored value exactly equals `RealPrice/mean(118 available RealE, prior-month window)`; the 40.4566 was a probe artifact using nominal P over a same-month 117-window. See §9.2.)
- `Rate GS10` 2026.09 = Sept 1 value.
- **Practical rule**: for research, **trailing 2–3 months are provisional**; drop or flag them, and re-pull each session.

## 8. Bond columns — RESOLVED (2026-09-17): BM is BR, stored one month early

The old §8 mystery ("BM erratic post-1950s, not the nominal/real twin of BR") was a **month-alignment
artifact**. The true relationship, exact to machine precision across **all 1867 rows**:

```
BM[i]  =  (BR[i+1]/BR[i]) · (CPI[i+1]/CPI[i])        # max rel. error 4.4e-16
```

i.e. **the value stored on row *i* is the *next month's* (month i+1) nominal total-return factor**
— BR's real growth for month i+1 inflated by month i+1's CPI ratio. Equivalently: BR's nominal
monthly factor on row *i* is `BM[i-1]` (with `BM[1871.01]` itself uncomputable — there is no
prior-month factor to anchor it, so BR is seeded at 1.0).

**Why the "post-1950s break" was visible at all.** Pre-1953 the GS10 column is a smooth
linearly-interpolated annual vintage (second differences = 0 within the year), so month *i*'s
factor and month *i+1*'s factor are nearly identical — the offset is invisible. From ~1953 GS10
genuinely moves monthly, so comparing BM row *i* against row *i*'s yield change
(`GS10[i]−GS10[i−1]`) mixes in the *next* month's price move: implied "duration" collapses from
≈8.3 to medians of 1.5–3.3, the BM/BR log-growth correlation reads ≈0.27 instead of 1.0000, and
months like 1981.11 "move opposite" (BM's 1981.11 cell holds *1981.12's* return, a −1.3% real month,
while BR's 1981.11 growth is +10.5%). Once BM is compared against month *i+1*'s yield change
(`GS10[i+1]−GS10[i]`), the price component tracks it at **−0.99** (post-1953) and implied duration
recovers ≈8 in **every** era (medians 8.31/8.36/8.22/6.70/7.71/8.81 — within 0.1 of BR's own).
Shiller's published bond formula (per the Bogleheads derivation of his method) uses
`Y_t/Y_{t+1}`-type terms — consistent with next-month yields driving the stored row.

**The blank last row falls out of this for free.** `BM[2026.09]` is blank because it would have to
be 2026.10's factor, which does not exist yet — not a missing or unpublished value.
`BM[2026.08]` already equals the 2026.09 factor exactly.

**Consequences / corrections to the old §8:**
- **BM and BR are the same underlying series** — one nominal monthly factor, one real cumulative
  index. Not two sources, not a formula change, not rounding.
- The old "BM min/max" (0.9174 @1980.01, 1.1090 @1981.10) are **1980.02's and 1981.11's** returns.
- The old "1981.11: BR +10.5% vs BM −0.7%" contradiction is the two cells straddling the offset.
- **To use BM as month *i*'s return, shift it down one row** (month i = `BM[i−1]`, i.e. the cell
  dated one month *before* the month the return applies to), or equivalently just **compute the
  nominal factor directly from BR**: `1+r_i = (BR[i]/BR[i−1])·(CPI[i]/CPI[i−1])`. This is
  exact and avoids the empty last cell.
- The "cannot rebuild BM or BR from GS10" finding still stands *as a price-level statement*:
  neither is reproducible from the GS10 *yield* column (BR/BM carry convexity and the full price
  path). But BM **is** fully reproducible from BR (identity above), and both share the same
  duration-≈8 price behavior in every era once aligned.

**Recommendation for the 60/40 study (updated):**
- Real bond returns: **BR** (levels/growth) — self-consistent, historically plausible, exact.
- Nominal monthly bond returns: compute `1+r_i = (BR[i]/BR[i−1])·(CPI[i]/CPI[i−1])` from BR.
  Cross-check against BM shifted down one row (exact by construction).
- Still consider an independent source (FRED DGS10 + documented duration/convexity model, or a
  vendor TR index) for a publishable study; treat Shiller's bond columns as the cross-check.

## 9. Open items — all resolved (spike complete)

Items 1–8 were the spike's open questions. All are now resolved or closed (item 8 moved to project planning). Kept as the record of what the spike settled.

1. ~~**BM post-1950s**~~ — **RESOLVED (2026-09-17).** BM is **not** a different series, formula, or
   rounding anomaly. **BM[i] = (BR[i+1]/BR[i])·(CPI[i+1]/CPI[i]) exactly** (max rel. err 4.4e-16,
   all 1867 rows): the value stored on row *i* is the **next month's** nominal total-return factor,
   i.e. BR's real growth for month i+1 inflated by month i+1's CPI. The "post-1950s break" was a
   month-alignment artifact (pre-1953 GS10 is smooth annual interpolation, hiding the offset;
   post-1953 monthly yields expose it). Aligned, BM's price component tracks GS10's *next-month*
   change at −0.99 and implied duration ≈8 in every era. Blank 2026.09 = no next month exists.
   See §8; `analysis/validate_data_md.py` now checks the identity + controls. External check
   (FRED DGS10/DTB3) still worthwhile as a cross-check, but no longer needed to *explain* BM.
2. ~~**Tail CAPE arithmetic**~~ — **RESOLVED (2026-09-17).** Stored 2026.09 CAPE (40.575838) **exactly** equals `RealPrice / mean(118 available RealE, trailing-120 ending prior month)` (diff 0.0). The earlier "mismatch" (40.4566) came from `probe13.py` using **nominal P** with a **same-month** 117-window — a probe artifact, not a file anomaly. No open question remains; the tail CAPE is computed with the same verified formula as the rest of the series, just over a partial (118/120) window.
3. ~~**CPI 2026.06 drop** (−1.17 pts)~~ — **RESOLVED (2026-09-17).** Verified against BLS: June 2026 CPI-U was **−0.4% SA** (−1.171 pts / −0.349% NSA), real energy-driven deflation (gasoline −9.7% SA); steepest NSA monthly drop since 2015.12 (−0.342%), and the only NSA decline in the 89 months 2019.01–2026.05. Estimate months now pinned exactly: **2026.08 & 2026.09 only** (2026.07 is the published actual 333.918, exact to FRED; BLS July release 2026-08-12 preceded the file's save). Shiller's Aug estimate (333.901) is ~1.08 below the actual 334.980 released 2026-09-11. The file's CPI column = BLS **unadjusted** CPI-U, exact to 3 decimals (2025.01→2026.07, 2025.10 gap excluded). See §7.
4. ~~**`Oct '25` in notes row**~~ — **RESOLVED (2026-09-17), and it's real, not stale template text.** BLS **never released October 2025 CPI** due to the 2025 government-shutdown lapse in appropriations (BLS's own releases state "The Oct 2025 data values are not available"; FRED has a gap at 2025.10; the Nov 2025 release reported a combined Sept–Nov change). Shiller's 2025.10 = 325.212 is his own fill-in (sits *above* both neighboring actuals). Cross-vintage check: the Yale mirror's 2023 file predates the shutdown and carries the older note `"Aug/Sept CPI estimated"`; the `Oct '25` term was added in later vintages. Bonus finding: the Yale mirror URL is **stale** (Last-Modified 2023-10-17) — use the shillerdata.com CDN (see §1.1).
5. ~~**D/12 assumption**~~ — **RESOLVED (2026-09-17).** D (and E) are the **annual (four-quarter) total** per-share $ flow, spread across the 12 months by Shiller's linear interpolation (his published note: "Monthly dividend and earnings data are computed from the S&P four-quarter totals for the quarters since 1926, with linear interpolation to monthly figures"). Three independent pieces of evidence, all in `analysis/validate_data_md.py`: (a) **yield magnitude** — reading D as the annual flow, `D/P` at year-end = 1.16%–2.20% for every year 2010–2025, matching the published S&P 500 dividend yield (1.50% 2023, 1.24% 2024, 1.15% 2025); reading it as a monthly flow, `12·D/P` = 13.9%–26.4%, implausible for any equity index. (b) **recursion uniqueness** — the RealTR recursion passes with 0 violations using `RD/12`; using `RD` as a full monthly flow fails 1865/1868 rows (max rel err 11%). (c) **interpolation structure** — D and E are flat within calendar quarters (within-quarter 2nd diffs ≤ 0.071 for 1926–2025) with kinks at quarter boundaries (≤ 0.071) plus small Dec→Jan kinks: consistent with interpolation across quarterly four-quarter-total knots, not with a true monthly flow. Footnote for the study: "Dividend" column = trailing four-quarter total per share, monthly values = Shiller's linear interpolation of the annual flow; RealTR uses D/12 as the monthly cash distribution (verified, §3 col 9).
6. ~~**Pre-1926 D/E interpolation quality**~~ — **RESOLVED (2026-09-17).** Pre-1926 D/E are **not**
   piecewise-constant — they are **linearly interpolated within each calendar year from annual
   knots** (Cowles). D changes every month in 46/55 years with *uniform* monthly increments
   (intra-year 2nd diffs ≤ 0.0001; E ≤ 0.0013, single outlier year 1916); only 9/55 years
   (D) / 3/55 (E) are fully constant (D: 1871, 1874, 1876, 1882, 1890, 1891, 1897, 1911, 1913;
   E: 1871, 1874, 1900). The only long flat runs are year-boundary overlaps where the annual
   knot is carried forward into the next year's first month (D = 0.33 across 1873.12–1874.12,
   0.30 across 1875.12–1876.12). Control: a step-function (piecewise-constant) reading has
   increment spread ~100× larger (0.119 for E 1920 vs observed max 0.0013) — the uniform
   increments decisively pick the linear reading. The 1925→1926 source splice (Cowles → S&P)
   is **smooth**: D/P 4.82%→4.80%, E/P 10.03%→9.87% (<0.5pt), so no level break at 1926.
   Pre-1926 median D/P by decade: 5.9% (1871s), 4.7% (1881s), 4.3% (1891s), 4.3% (1901s),
   5.7% (1911s), 6.0% (1921s) — same order as 1926–1990 (med 4.3%). **Verdict for the 60/40
   study:** usable for long-run return math. The only real approximations are (a) the
   within-year linear ramp (the annual knot is a modest, known distortion of monthly
   dividends) and (b) the W&P-spliced CPI in the same window (§6) — the double-approximation
   era flagged in the original question, but neither produces a level break at the splice.
   All quantified in `analysis/validate_data_md.py` (§9 item 6 block, 6 checks).
7. ~~**Pull current file at session start + record vintage**~~ — **DONE (2026-09-17); now a standing procedure.** Vintage ledger lives in `data/RUNLOG.md` (entry per pull: sha256, last-saved stamp, last row, K, notes row, suite result, delta vs last entry). First entry: file is **byte-identical** to the §1.1 pin (sha256 `044196da…89c1`; last saved 2026-09-02 14:25:11 OLE; last row 2026.09; K = 333.8925; notes row `Sept price is Sept 1st close` / `Oct '25/Aug/Sept CPI estimated` / `Sept GS10 is Sept 1st value`; suite 81/81). **Every session:** pull per §1.1, append an entry, and if the hash changed — diff, re-run the suite, and update §1.1 + vintage-sensitive numbers in this doc.
8. ~~**Decide canonical 60/40 construction**~~ — **MOVED OUT OF SCOPE (2026-09-17).** Design call, belongs to project planning, not the data spike. The inputs are settled in this doc: real 60/40 = RealTR × BR-growth; nominal bond 1+r from BR via `(BR[i]/BR[i−1])·(CPI[i]/CPI[i−1])` (§8); nominal equity TR constructible from P + D (D = annual four-quarter flow, D/12 monthly, §9 item 5).

## 10. Reading recipe (pinned to this file layout)

```python
import xlrd, math
wb = xlrd.open_workbook("data/ie_data.xls")          # xlrd 2.x reads .xls
d = wb.sheet_by_name("Data")
rows = [[c for c in d.row_values(r)] for r in range(8, d.nrows - 1)]  # data rows (0-idx 8-1876); row 7 = header, last row = notes
def f(v):
    if isinstance(v, str) and (v.strip() in ("", "NA")): return None
    return float(v)
# col 0: date → year=int(dt), month=round((dt-year)*100)
# use: RealTR (9) real equity TR; BR (18) real bond cum index
#       nominal bond 1+r for month i = (BR[i]/BR[i-1])*(CPI[i]/CPI[i-1])
#       (col 17 "BM" = that factor for month i+1, stored one row early; blank last row)
# K = CPI[-1] for all real columns; CAPE window = trailing 120 ending PRIOR month
```

Probes: all original ad-hoc probes are archived in `analysis/_archive/` (see its README for known bugs and what each covered). The maintained regression suite is `analysis/validate_data_md.py` — re-derives every quantitative claim in this file (81 checks; run with the project venv, exits non-zero on any failure). Note: real levels (all §4 "K"-scaled columns) are pinned to this file's vintage; re-run the suite after each re-pull.
