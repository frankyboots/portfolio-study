# The Portfolio Study

One 60/40 portfolio, held for 150 years, in real and nominal terms — built
from one pinned data file, so that every number on the published site
reproduces byte-for-byte from the commit that stamped it.

## Hero exhibit

![Line chart of the real 60/40 growth index (monthly-rebalanced), January 1871 to June 2026. Axes: Year, Growth of $1, log scale. Real 60/40 (monthly-rebalanced) grows from 1.00 at January 1871 to 3,868 at June 2026, plotted on a log scale: equal slopes are equal growth rates. Extremes: the minimum is 0.983 at February 1871; the maximum is 3,868 at June 2026, the terminal value. 13 hatched bands mark the drawdown episodes of 15% or worse in real terms (peak-to-new-high stretches; the count is computed from the episodes artifact and stated in the keep-out band): hatch-only data-bad strokes, transparent fill. 2 series: the real growth line (primary, solid) and the drawdown bands (band, hatched).](artifacts/figures/hero_real_growth_v1.png)

Published at [its permalink](https://frankyboots.github.io/portfolio-study/#hero_real_growth_v1).
The exports are committed, so the exhibit above is visible without building
anything; the baked release stamp on the image is the build's machine-readable
label (vintage, build-head, builder module).

## Reproduce this

From a clean clone, on the pinned Python environment:

1. **Pin the build.** Check out the commit named in the figure's baked
   `BUILD-HEAD` stamp — the stamp on the exported image above.
2. **Pull the data.** `data/ie_data.xls` is not committed (the source site's
   license), so pull it per [`data/RUNLOG.md`](data/RUNLOG.md). A fresh
   checkout without it cannot run the validation suite — that failure is
   deliberate and named.
3. **Run the pipeline.** `uv sync`, then `uv run python scripts/pipeline.py`.
   The pipeline sets its own deterministic runtime envelope (pinned fonts,
   hash salt, locked canvas), rebuilds every data artifact from the pulled
   file, re-stamps the exports, and runs the Edition gates — the
   export-freshness gate last, proving the regenerated figure matches the
   committed one in every non-stamp byte.
4. **Build the site.** `cd web && npm ci && npm run build` — the site binds
   only to the manifest, the committed figure records, and the committed
   drawdown-episodes artifact.

The data artifacts (the monthly series CSV and the drawdown-episodes CSV)
reproduce byte-identically; that is the promise the gates check, not a claim
to eyeball.

## What the study is

A study of a 60/40 portfolio — 60% equity, 40% long-term nominal bond,
monthly-rebalanced — over 150 years of Shiller US data, in real and nominal
terms. The published exhibits are the ground truth for its numbers; this
repository is how they are proven. Construction conventions (the leg factors,
the rebalancing rules, the drawdown-episode definition) and the
vintage/reproduce chain are written down in
[`docs/methodology.md`](docs/methodology.md).

## Audit trail

- **Methodology** — [`docs/methodology.md`](docs/methodology.md): how the
  series are built, how drawdown episodes are defined, and how a number on
  the site traces back to a pinned file.
- **Validation suite** — `analysis/validate_data_md.py`: the machine check
  that the dataset's pinned description still matches the file on disk; a
  pipeline gate, and the first thing to run after any re-pull.
- **Vintage Ledger** — [`data/RUNLOG.md`](data/RUNLOG.md): one entry per data
  pull; the vintage-integrity gate verifies the ledger covers the file that
  is on disk.
- **Dataset semantics** — [`data/DATA.md`](data/DATA.md): every column's
  verified meaning, the re-basing quirk that makes real levels
  vintage-dependent, and the provenance pin.
- **Pull & run procedure** — [`data/RUNLOG.md`](data/RUNLOG.md): how to pull
  the data file and the re-pull procedure that keeps `DATA.md` honest.

## Layout, license

- `analysis/` — the layers: `series` (data artifacts) → `metrics` (derived
  data artifacts) → `figures` (exhibit exports).
- `scripts/` — the pipeline and its Edition gates.
- `data/` — the pinned dataset description and the vintage ledger.
- `artifacts/` — the committed outputs (data artifacts, figure exports,
  records) and the root `manifest.json`.
- `web/` — the published site (static Astro; binds to the manifest and the
  committed records only).
- `docs/` — the methodology.
- `tests/` — the suite the pipeline runs as a gate.

Code and pipeline: MIT (`LICENSE`). Study content: all rights reserved.
