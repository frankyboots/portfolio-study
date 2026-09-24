# Methodology

How this study builds its 60/40 series, defines drawdown episodes, and ties
every published number back to a pinned data vintage. The source dataset's
column semantics are pinned and verified in `data/DATA.md`; this document
states the construction conventions on top of that pinned input. It is a
gate-6 surface: any vintage fact it names (file hash, the rebasing constant,
the final data row) is referenced into `data/DATA.md`, never restated here.

## 1. Source dataset

One Shiller `ie_data.xls` (IE dataset), pulled per `data/RUNLOG.md`. Dataset
dates are the decimal `YYYY.MM` convention (`1871.1` = the first month of
1871). The single on-disk copy is pinned by a pipeline run: its file hash,
final data row, and rebasing constant are stamped into the `vintage` block of
every artifact sidecar and into the root `manifest.json`, so one run's outputs
are only ever read against that run's pinned input.

## 2. The 60/40 legs (shared engine)

Both published series — the monthly-rebalanced canonical series and the
calendar-year-end-rebalanced comparator — draw their per-month leg factors
from one shared engine (`analysis/series/legs.py`), so the two rebalancing
conventions can never diverge through a second construction of the legs:

- **Real legs.** Equity = the Real Total-Return Price (dataset col 9) growth
  factor; bond = the Real Total Bond Returns index (col 18) growth factor.
- **Nominal legs.** Equity month factor = `(P + D/12) / P_prev`. `D` is the
  trailing four-quarter dividend dollar amount spread across the year, so
  `D/12` is the month's cash dividend (dataset col 2; `DATA.md` §3). Bond
  month factor = the "Monthly Total Bond Returns" column (col 17) shifted down
  one row — that column stores the *next* month's nominal factor one row early
  (`DATA.md` §8), so month `i` reads `BM[i-1]`.
- **Identity cross-check.** The shifted bond factor is re-derived every month
  as `(BR[i]/BR[i-1]) · (CPI[i]/CPI[i-1])` and matched to the stored column at
  relative tolerance `1e-12`; a mismatch is a build failure. This guards both
  the one-month lead and the read.
- **Endpoint.** The series runs to the last month where every construction
  input is present; trailing months with a blank required input are excluded
  and recorded with reasons in the sidecar's `excluded_provisional` list. A
  blank required input *inside* the used range is a build failure, never a
  silent exclusion.

## 3. Rebalancing rules

- **Monthly (the canonical series).** The 0.6/0.4 weights are re-imposed every
  return month; the month factor is the weighted leg average
  `0.6 · equity + 0.4 · bond`. Both the real and nominal growth indices are
  seeded at `1.0` in the seed month.
- **Calendar-year-end (the comparator).** The weights reset to 0.6/0.4 in the
  first return month of each calendar year; within the year they drift with
  leg growth. The rebalance-diff artifact is the annual-rebalanced level minus
  the monthly-rebalanced level, month by month (growth-index points).

Because both consume the one leg engine, the monthly/annual divergence is the
rebalancing rule alone.

## 4. Drawdown episodes (metrics layer)

A drawdown episode is a peak-to-new-high "underwater" stretch over the real
monthly growth index, computed by `analysis/metrics/drawdown.py`:

- The running peak is seeded at the first month.
- An **episode opens** when the index falls strictly below the running peak
  (a float-noise epsilon guards the comparison).
- The episode tracks its worst trough.
- It **closes** at the first month the index reaches the peak again (a new
  high).
- It **qualifies** when its depth `1 − trough/peak` is at least `0.15`
  inclusive (a 15% drawdown).
- A qualifying episode still open at the series tail is kept, with its
  recovery fields left empty in the CSV.

The threshold (`0.15`), epsilon, and this algorithm are recorded in the
episodes sidecar's `episodes` block. The hero figure's hatched bands, its
keep-out count, and its alt text all derive from this single computed
artifact in one run — the episode count is a build-computed value, never a
hand-typed constant, and is deliberately not reconciled against any
pre-picked number.

## 5. Vintage and the reproduce chain

Every "Real" column in the source file is deflated with a constant equal to
the file's final CPI — the re-basing quirk pinned in `DATA.md` §4. The
consequence is load-bearing: real levels are comparable only *within one file
vintage*, because each monthly re-release silently rescales the entire real
history. All long-run return math here is done on ratios and growth factors,
which are invariant across vintages; the pinned `K` (the rebasing constant)
and the file hash live in `data/DATA.md` §1.1 / §4, not in this document.

The chain that a stranger follows to reproduce every number on the site:

1. Clone the repository and pin the exact build: check out the commit named by
   a figure's baked `BUILD-HEAD` stamp.
2. Pull `ie_data.xls` per `data/RUNLOG.md` (a fresh checkout without it cannot
   run the validation suite — the data file is not committed, by license).
3. Run the pinned pipeline: `uv sync`, then `uv run python scripts/pipeline.py`.

The pipeline sets its own deterministic runtime envelope (pinned fonts,
deterministic hash salt, locked canvas), rebuilds every data artifact from the
pinned input, and re-stamps the exports. The export-freshness gate then proves
a regenerated figure matches the committed one byte-for-byte outside the
stamp region.

## 6. Audit trail (filing-cabinet entries)

- **Methodology** — this document: construction conventions, the episode
  definition, and the vintage/reproduce chain.
- **Validation suite** — `analysis/validate_data_md.py`: the machine check that
  `data/DATA.md` still describes the on-disk file; it is a pipeline gate.
- **Vintage Ledger** — `data/RUNLOG.md`: one entry per `ie_data.xls` pull; the
  integrity gate verifies the ledger covers the on-disk vintage.
- **Dataset semantics** — `data/DATA.md`: every column's verified meaning, the
  re-basing quirk, and the provenance pin (hash, `K`, final data row).
- **Pull & run procedure** — `data/RUNLOG.md`: how to pull the data and the
  re-pull procedure that keeps `DATA.md` current.
