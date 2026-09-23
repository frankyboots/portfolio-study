# RUNLOG — ie_data.xls vintage ledger

One entry per pull (per DATA.md §9 item 7). Real levels are vintage-dependent
(K = last CPI re-bases every real column), so any number quoted from the
dataset is only valid against the vintage it was measured in.

**Vintage governance (mechanized, story 1.4; owner `analysis/vintage_ledger.py`):**

- **Ledger cadence:** a machine entry is appended only when the latest ledger
  entry does not *cover* the on-disk vintage — covers = the latest entry's
  `sha256:` field equals the file on disk (and therefore the pin in any
  pipeline run). Steady runs verify the binding and append nothing; the gate
  pass *is* the binding verification (disk sha256 == pin == latest entry ==
  every artifact sidecar stamp). The suite subprocess runs only when an
  append is needed.
- **Two append paths share one renderer:** the recorder CLI
  (`uv run python scripts/record_vintage.py [root]`) for the pre-pin-update
  window, and the pipeline's `vintage-integrity` stage as the LATEST-STALE
  fallback (the pin was already updated without a recorder run).
- **The gate** fails the build on any cross-vintage mix: `MIXED-STAMPS` (a
  sidecar `vintage.sha256` outside `{pin} ∪ logged overrides`), `UNSTAMPED`
  (a sidecar without a valid `vintage.sha256`), `DISK-DRIFT` (on-disk
  sha256 ≠ pin, or the file missing), and `LATEST-STALE` (the latest ledger
  entry does not cover the on-disk vintage). It runs as pipeline stage
  `vintage-integrity` (after the artifact stages, so a legitimate full
  rebuild regenerates all stamps before judgment) and standalone:
  `uv run python scripts/check_vintage_integrity.py [root]`.
- **Override stanza:** a strict stanza the human appends to an entry — an
  amendment, not a new entry (cadence unaffected). One bullet, shas
  space-separated, full 64-hex each:
  `- override: allow-vintages <sha256>… — reason: <text> — logged by: <name> — date: YYYY-MM-DD`
  The gate passes iff every distinct sidecar stamp sha ∈ `{pin} ∪` the union
  of all `allow-vintages` sets, and on pass it prints the matching
  stanza(s). Removal is a human edit, visible in git history.

**Machine entry format** (rendered byte-for-byte; machine entries omit the
human-only extras the seed entry carried — last P, GS10 note, doc-normalized
stamp — and the notes row is the verbatim sheet cell, segments joined with
` / `):

```
## YYYY-MM-DD — pull from shillerdata.com CDN
- sha256: <full hash> (<N> bytes) — same/changed vs §1.1 pin; same/changed vs last entry
- last saved: <stamp> by <author>; created <date>
- last row: YYYY.MM; K (last CPI): <K>
- notes row: <verbatim sheet cell>
- suite: <n>/<m> pass | <n>/<m> pass, <f> FAILED — as run at record time
- delta: none (first ledger entry) | none (identical bytes to the pinned vintage) | sha256 <old> → <new>; K <old> → <new>; last row <old> → <new>; cell-by-cell diff: PENDING (human step)
```

**Pull procedure** (DATA.md §1.1):
1. Scrape `https://shillerdata.com/` for the current CDN blob href (`?ver=` rotates).
2. Download to `data/ie_data.xls`; compare `sha256` + byte size against the §1.1 pin and the last entry below.
3. Record the pull: `uv run python scripts/record_vintage.py` — it reads BIFF metadata (olefile
   `get_metadata()`) + last-row date + K = last CPI + the notes row from the file on disk (pin
   bypassed: a re-pulled file never matches the pin yet), runs
   `analysis/validate_data_md.py`, and appends the machine entry with the
   machine-computed delta vs the prior entry. A changed vintage's delta records
   the machine-verifiable deltas and marks the full diff PENDING (human step).
4. Do the human steps that `scripts/record_vintage.py` prints: update the §1.1 pin (`shiller_io.VINTAGE_SHA256`
   + DATA.md), re-verify DATA.md's vintage-sensitive numbers (K, last-row stats, tail
   estimates), and complete the PENDING cell-by-cell diff.
5. Rebuild: `uv run python scripts/pipeline.py` (the step `scripts/record_vintage.py`
   prints) regenerates `artifacts/series/` from the new vintage (the endpoint is
   content-driven, so the endpoint/row count can move), the suite byte-checks the
   committed CSV against its in-memory reconstruction, and the pipeline's
   `vintage-integrity` stage re-verifies the full binding before it exits 0.

---

## 2026-09-17 — pull from shillerdata.com CDN (first log)

- sha256: `044196dafe44c3030b2facbdea023975b3f6aa68b4e52f8f9bafc403e19589c1` (1,674,752 bytes) — **same as §1.1 pin**; file unchanged since the 2026-09-17 validation
- last saved: 2026-09-02 14:25:11 (OLE; doc-normalized Wed Sep 2 15:25:11 2026) by `Laurence Black`; created 2000-07-15; author `RShiller`
- last row: **2026.09**; K (last CPI): **333.8925**; last P 7631.47; D/E blank 2026.07–09; GS10 4.75 (Sept 1st value)
- notes row: `Sept price is Sept 1st close` / `Oct '25/Aug/Sept CPI estimated` / `Sept GS10 is Sept 1st value`
- suite: 81/81 pass (`.venv/bin/python analysis/validate_data_md.py`)
- delta: none (identical bytes to the pinned vintage)
