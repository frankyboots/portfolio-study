# RUNLOG — ie_data.xls vintage ledger

One entry per pull (per DATA.md §9 item 7). Real levels are vintage-dependent
(K = last CPI re-bases every real column), so any number quoted from the
dataset is only valid against the vintage it was measured in.

**Pull procedure** (DATA.md §1.1):
1. Scrape `https://shillerdata.com/` for the current CDN blob href (`?ver=` rotates).
2. Download; compute `sha256` + byte size; compare against §1.1 pin and the last entry below.
3. Read BIFF metadata (olefile `get_metadata()`) + last-row date + K = last CPI.
4. Run `analysis/validate_data_md.py` (92 checks) against the file on disk.
5. Append an entry. If the file changed since the last entry: re-run the suite
   (it was verified against the old vintage), diff cell-by-cell, and update
   DATA.md §1.1 pin + any vintage-sensitive numbers (K, last-row stats, tail
   estimates). Also rebuild and re-commit the series artifacts: the pipeline's
   `series` stage (`uv run python scripts/pipeline.py`) regenerates
   `artifacts/series/` from the new vintage (the endpoint is content-driven,
   so the endpoint/row count can move), and the suite byte-checks the
   committed CSV against its in-memory reconstruction.

**Entry format:**

```
## YYYY-MM-DD — pull from <source>
- sha256: <full hash> (<N> bytes) — same/changed vs §1.1 pin / last entry
- last saved: <stamp> by <author>; created 2000-07-15
- last row: YYYY.MM; K (last CPI): <K>
- notes row: <verbatim>
- suite: <n>/92 pass
- delta: none | list of changed cells/columns and what it implies
```

---

## 2026-09-17 — pull from shillerdata.com CDN (first log)

- sha256: `044196dafe44c3030b2facbdea023975b3f6aa68b4e52f8f9bafc403e19589c1` (1,674,752 bytes) — **same as §1.1 pin**; file unchanged since the 2026-09-17 validation
- last saved: 2026-09-02 14:25:11 (OLE; doc-normalized Wed Sep 2 15:25:11 2026) by `Laurence Black`; created 2000-07-15; author `RShiller`
- last row: **2026.09**; K (last CPI): **333.8925**; last P 7631.47; D/E blank 2026.07–09; GS10 4.75 (Sept 1st value)
- notes row: `Sept price is Sept 1st close` / `Oct '25/Aug/Sept CPI estimated` / `Sept GS10 is Sept 1st value`
- suite: 81/81 pass (`.venv/bin/python analysis/validate_data_md.py`)
- delta: none (identical bytes to the pinned vintage)
