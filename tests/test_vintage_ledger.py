"""Story 1.4: vintage governance — the RUNLOG ledger and the integrity gate.

The full I/O matrix on staged tmp roots (steady state, new vintage,
LATEST_STALE, MIXED_STAMPS, UNSTAMPED, DISK_DRIFT, OVERRIDE), plus exact
entry bytes, delta strings, strict stanza parsing, canned suite-stdout
parsing, and the pin-bypass facts path. Staged roots keep the repo
untouched; the real validation suite runs as a subprocess only on the
append paths (LATEST_STALE), never on steady-state checks.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

from analysis import vintage_ledger as vl
from analysis.series import shiller_io

REPO_ROOT = Path(__file__).resolve().parents[1]
PIN = shiller_io.VINTAGE_SHA256
OLD_SHA = "c" * 64
OTHER_SHA = "b" * 64
NEW_SHA = "e" * 64
GATE_CLI = REPO_ROOT / "scripts" / "check_vintage_integrity.py"
RECORDER_CLI = REPO_ROOT / "scripts" / "record_vintage.py"

SIDECAR_NAMES = (
    "canonical_60_40_monthly_v1.meta.json",
    "canonical_60_40_annual_v1.meta.json",
    "canonical_60_40_rebalance_diff_v1.meta.json",
)

#: An old-vintage entry: full pin-shape fields, emphasis as the seed entry
#: carries them, sha != the pin (so steady-state coverage is testable).
OLD_ENTRY = f"""\
## 2026-09-17 — pull from shillerdata.com CDN (first log)
- sha256: `{OLD_SHA}` (1,674,752 bytes) — **changed vs §1.1 pin**; file re-pulled
- last row: **2026.08**; K (last CPI): **332.1**; last P 7600.00
- notes row: Aug price is Aug 1st close
- suite: 81/81 pass
- delta: none (first ledger entry)
"""

#: A covering entry: its sha256 equals the pin, so the on-disk vintage is
#: on record and only the stamped mix itself can fail the gate.
COVERING_ENTRY = f"""\
## 2026-09-17 — pull from shillerdata.com CDN (first log)
- sha256: `{PIN}` (1,674,752 bytes) — **same as §1.1 pin**; file unchanged
- last row: **2026.09**; K (last CPI): **333.8925**
- suite: 81/81 pass
- delta: none (identical bytes to the pinned vintage)
"""


def stage_repo(
    tmp_path: Path,
    *,
    runlog_text: str | None = None,
    mutate_sidecar: str | None = None,
    drop_sidecar_vintage: str | None = None,
    corrupt_xls: bool = False,
) -> Path:
    """Stage a repo-shaped tmp root the ledger machinery can operate on."""
    root = tmp_path / "repo"
    for name in ("scripts", "analysis", "config"):
        shutil.copytree(
            REPO_ROOT / name,
            root / name,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    data = root / "data"
    data.mkdir()
    shutil.copy2(REPO_ROOT / "data" / "ie_data.xls", data / "ie_data.xls")
    if corrupt_xls:
        blob = bytearray((data / "ie_data.xls").read_bytes())
        blob[-1] ^= 0x01  # wrong bytes: disk sha now differs from the pin
        (data / "ie_data.xls").write_bytes(bytes(blob))
    runlog = data / "RUNLOG.md"
    if runlog_text is not None:
        runlog.write_text(runlog_text, encoding="utf-8")
    else:
        shutil.copy2(REPO_ROOT / "data" / "RUNLOG.md", runlog)
    arts = root / "artifacts" / "series"
    arts.mkdir(parents=True)
    for name in SIDECAR_NAMES:
        text = (REPO_ROOT / "artifacts" / "series" / name).read_text(encoding="utf-8")
        if mutate_sidecar == name:
            text = text.replace(PIN, OTHER_SHA)
        if drop_sidecar_vintage == name:
            obj = json.loads(text)
            del obj["vintage"]
            text = json.dumps(obj, indent=2, sort_keys=True) + "\n"
        (arts / name).write_text(text, encoding="utf-8")
    return root


def run_gate(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GATE_CLI), str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


def run_recorder(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RECORDER_CLI), str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


# ---------------------------------------------------------------- entry bytes


def test_render_entry_exact_bytes_changed_delta() -> None:
    facts = vl.VintageFacts(
        sha256=NEW_SHA,
        byte_size=1674800,
        last_saved="2026-10-01 12:00:00",
        last_saved_by="Laurence Black",
        created="2000-07-15",
        last_row="2026.10",
        k=334.1,
        notes_row="Oct price is Oct 1st close / Oct CPI estimated",
    )
    previous = vl.LedgerEntry(
        date="2026-09-17", sha256=OLD_SHA, k="332.1", last_row="2026.08"
    )
    entry = vl.render_entry(
        facts,
        pin=PIN,
        previous=previous,
        record_date=date(2026, 10, 5),
        suite_line="99/101 pass, 2 FAILED",
    )
    assert entry == (
        "## 2026-10-05 — pull from shillerdata.com CDN\n"
        f"- sha256: {NEW_SHA} (1,674,800 bytes) — changed vs §1.1 pin; "
        f"changed vs last entry\n"
        "- last saved: 2026-10-01 12:00:00 by Laurence Black; created 2000-07-15\n"
        "- last row: 2026.10; K (last CPI): 334.1\n"
        "- notes row: Oct price is Oct 1st close / Oct CPI estimated\n"
        "- suite: 99/101 pass, 2 FAILED — as run at record time\n"
        f"- delta: sha256 {OLD_SHA} → {NEW_SHA}; K 332.1 → 334.1; "
        f"last row 2026.08 → 2026.10; "
        f"cell-by-cell diff: PENDING (human step)\n"
    )


def test_render_entry_first_entry_delta() -> None:
    facts = vl.VintageFacts(
        sha256=PIN,
        byte_size=1674752,
        last_saved="2026-09-02 14:25:11",
        last_saved_by="Laurence Black",
        created="2000-07-15",
        last_row="2026.09",
        k=333.8925,
        notes_row="Sept price is Sept 1st close",
    )
    entry = vl.render_entry(
        facts,
        pin=PIN,
        previous=None,
        record_date=date(2026, 9, 22),
        suite_line="101/101 pass",
    )
    assert entry.splitlines()[-1] == "- delta: none (first ledger entry)"
    assert entry.splitlines()[1] == (
        f"- sha256: {PIN} (1,674,752 bytes) — same as §1.1 pin; no prior ledger entry"
    )


def test_render_entry_latest_stale_delta() -> None:
    """The fallback append: recorded bytes equal the pin, prior entry differs."""
    facts = vl.VintageFacts(
        sha256=PIN,
        byte_size=1674752,
        last_saved="2026-09-02 14:25:11",
        last_saved_by="Laurence Black",
        created="2000-07-15",
        last_row="2026.09",
        k=333.8925,
        notes_row="Sept price is Sept 1st close",
    )
    previous = vl.LedgerEntry(
        date="2026-09-17", sha256=OLD_SHA, k="332.1", last_row="2026.08"
    )
    entry = vl.render_entry(
        facts,
        pin=PIN,
        previous=previous,
        record_date=date(2026, 9, 22),
        suite_line="101/101 pass",
    )
    assert entry.splitlines()[1] == (
        f"- sha256: {PIN} (1,674,752 bytes) — same as §1.1 pin; changed vs last entry"
    )
    assert entry.splitlines()[-1] == (
        "- delta: none (identical bytes to the pinned vintage)"
    )


# ---------------------------------------------------------------- parsing


def test_parse_suite_summary_canned() -> None:
    assert vl.parse_suite_summary(
        "...lots of PASS lines...\n\n81/81 passed, 0 failed\n"
    ) == ("81/81 pass")
    assert (
        vl.parse_suite_summary(
            "[PASS] x  | d\n[FAIL] y  | d\n\n99/101 passed, 2 failed\n"
        )
        == "99/101 pass, 2 FAILED"
    )
    try:
        vl.parse_suite_summary("no summary line here")
    except vl.LedgerError:
        pass
    else:
        raise AssertionError("expected LedgerError for a summary-less output")


def test_parse_stanzas_strict() -> None:
    good = (
        OLD_ENTRY + f"- override: allow-vintages {OTHER_SHA} {NEW_SHA} — "
        "reason: mid-epoch rebuild in flight — logged by: Frank — date: 2026-10-01\n"
    )
    _, stanzas = vl.parse_ledger(good)
    assert stanzas == [
        vl.OverrideStanza(
            raw=f"- override: allow-vintages {OTHER_SHA} {NEW_SHA} — "
            "reason: mid-epoch rebuild in flight — logged by: Frank — "
            "date: 2026-10-01",
            shas=(OTHER_SHA, NEW_SHA),
            reason="mid-epoch rebuild in flight",
            logged_by="Frank",
            date="2026-10-01",
        )
    ]
    for bad in (
        # short sha (not full 64-hex)
        OLD_ENTRY
        + f"- override: allow-vintages {OTHER_SHA[:55]} — reason: r — logged by: n — date: 2026-10-01\n",
        # missing the date field
        OLD_ENTRY
        + f"- override: allow-vintages {OTHER_SHA} — reason: r — logged by: n\n",
        # indented sub-bullet, not a top-level entry bullet
        OLD_ENTRY
        + f"  - override: allow-vintages {OTHER_SHA} — reason: r — logged by: n — date: 2026-10-01\n",
        # stanza outside any entry
        f"- override: allow-vintages {OTHER_SHA} — reason: r — logged by: n — date: 2026-10-01\n",
    ):
        assert vl.parse_ledger(bad)[1] == [], bad


def test_parse_ledger_seed_entry_and_backfill_entry() -> None:
    entries, _ = vl.parse_ledger(
        (REPO_ROOT / "data" / "RUNLOG.md").read_text(encoding="utf-8")
    )
    # Two committed entries: the 2026-09-17 seed and the backfilled
    # 2026-09-22 byte-identical pull (the latest).
    assert len(entries) == 2
    seed, latest = entries
    assert seed.date == "2026-09-17"
    assert seed.sha256 == PIN  # backticks in the seed entry are tolerated
    assert seed.k == "333.8925"  # ** emphasis is tolerated
    assert seed.last_row == "2026.09"
    assert latest.date == "2026-09-22"  # the backfill entry covers the disk vintage
    assert latest.sha256 == PIN
    assert latest.k == "333.8925"
    assert latest.last_row == "2026.09"

    entries, _ = vl.parse_ledger(OLD_ENTRY)
    assert entries[0] == vl.LedgerEntry(
        date="2026-09-17", sha256=OLD_SHA, k="332.1", last_row="2026.08"
    )


# ---------------------------------------------------------------- facts path


def test_facts_path_bypasses_pin_and_reads_disk(tmp_path: Path, monkeypatch) -> None:
    root = stage_repo(tmp_path)
    seen: dict[str, object] = {}
    real = shiller_io.load_vintage

    def spy(root_arg: Path, pin: str | None = shiller_io.VINTAGE_SHA256) -> object:
        seen["pin"] = pin
        return real(root_arg)

    monkeypatch.setattr(shiller_io, "load_vintage", spy)
    facts = vl.read_vintage_facts(root)
    assert seen["pin"] is None  # the pin-optional facts path, recorder-only
    assert facts.sha256 == PIN
    assert facts.last_row == "2026.09"
    assert facts.k == 333.8925
    assert "Sept price is Sept 1st close" in facts.notes_row
    assert "Oct '25/Aug/Sept CPI estimated" in facts.notes_row
    assert facts.last_saved_by == "Laurence Black"
    assert facts.created == "2000-07-15"
    assert facts.last_saved.startswith("2026-09-02 14:25:1")


def test_facts_path_reads_file_whose_sha_differs_from_pin(tmp_path: Path) -> None:
    """Pin-optional path against bytes whose real sha differs from the pin.

    Stages a flipped byte so the on-disk sha genuinely is not the pin; the
    facts path must read it anyway and report the file's real sha256. (If
    ``shiller_io.load_vintage``'s pin guard regressed to unconditional,
    ``read_vintage_facts`` would raise and this test would fail.)
    """
    root = stage_repo(tmp_path, corrupt_xls=True)
    real_sha = hashlib.sha256(
        root.joinpath(*shiller_io.XLS_RELPATH).read_bytes()
    ).hexdigest()
    assert real_sha != shiller_io.VINTAGE_SHA256
    facts = vl.read_vintage_facts(root)
    assert facts.sha256 == real_sha
    assert facts.last_row == "2026.09"


# ---------------------------------------------------------------- matrix: gate


def test_matrix_steady_state(tmp_path: Path) -> None:
    root = stage_repo(tmp_path)
    result = run_gate(root)
    assert result.returncode == 0, result.stderr
    assert "OK: vintage integrity" in result.stdout
    assert "OVERRIDE STANZA" not in result.stdout


def test_matrix_disk_drift(tmp_path: Path) -> None:
    root = stage_repo(tmp_path, corrupt_xls=True)
    result = run_gate(root)
    assert result.returncode == 1
    assert "DISK-DRIFT" in result.stderr
    assert PIN in result.stderr
    assert re.search(r"[0-9a-f]{64}", result.stderr)  # the drifted sha is named


def test_matrix_mixed_stamps(tmp_path: Path) -> None:
    root = stage_repo(tmp_path, mutate_sidecar=SIDECAR_NAMES[0])
    result = run_gate(root)
    assert result.returncode == 1
    assert "MIXED-STAMPS" in result.stderr
    assert "canonical_60_40_monthly_v1.meta.json" in result.stderr
    assert OTHER_SHA in result.stderr
    assert PIN in result.stderr  # both shas are named


def test_matrix_unstamped(tmp_path: Path) -> None:
    root = stage_repo(tmp_path, drop_sidecar_vintage=SIDECAR_NAMES[1])
    result = run_gate(root)
    assert result.returncode == 1
    assert "UNSTAMPED" in result.stderr
    assert "canonical_60_40_annual_v1.meta.json" in result.stderr


def test_matrix_latest_stale(tmp_path: Path) -> None:
    """Gate fails pre-append; the shared append path fixes it; steady after."""
    root = stage_repo(tmp_path, runlog_text=OLD_ENTRY + "\n")
    result = run_gate(root)
    assert result.returncode == 1
    assert "LATEST-STALE" in result.stderr

    # The pipeline's fallback appends via the shared renderer (real suite run).
    assert vl.ensure_ledger_covers_vintage(root) is True
    text = (root / "data" / "RUNLOG.md").read_text(encoding="utf-8")
    assert f"- sha256: {PIN} (" in text
    assert "- delta: none (identical bytes to the pinned vintage)" in text
    assert re.search(r"- suite: \d+/\d+ pass — as run at record time", text)
    result = run_gate(root)
    assert result.returncode == 0, result.stderr
    # Steady now: the fallback is a no-op and re-runs no suite subprocess.
    assert vl.ensure_ledger_covers_vintage(root) is False
    assert vl.ensure_ledger_covers_vintage(root) is False


def test_matrix_override(tmp_path: Path) -> None:
    root = stage_repo(
        tmp_path,
        mutate_sidecar=SIDECAR_NAMES[0],
        runlog_text=COVERING_ENTRY
        + f"\n- override: allow-vintages {OTHER_SHA} — reason: mid-epoch rebuild in "
        "flight — logged by: Frank — date: 2026-10-01\n",
    )
    # Without the stanza the same mix fails...
    no_stanza = stage_repo(tmp_path / "x", mutate_sidecar=SIDECAR_NAMES[0])
    assert run_gate(no_stanza).returncode == 1
    # ...with the logged stanza the gate exits 0 and announces the stanza.
    result = run_gate(root)
    assert result.returncode == 0, result.stderr
    assert "OK: vintage integrity" in result.stdout
    assert "OVERRIDE STANZA IN FORCE" in result.stdout
    assert f"allow-vintages {OTHER_SHA}" in result.stdout


def test_gate_usage_errors() -> None:
    usage = subprocess.run(
        [sys.executable, str(GATE_CLI), "a", "b"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert usage.returncode == 2
    missing = subprocess.run(
        [sys.executable, str(GATE_CLI), "/no/such/dir"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert missing.returncode == 2


# ---------------------------------------------------------------- matrix: recorder


def test_matrix_recorder_noop_on_steady_tree(tmp_path: Path) -> None:
    root = stage_repo(tmp_path)
    before = (root / "data" / "RUNLOG.md").read_bytes()
    result = run_recorder(root)
    assert result.returncode == 0, result.stderr
    assert "no-op" in result.stdout
    assert "already covers the on-disk vintage" in result.stdout
    assert (root / "data" / "RUNLOG.md").read_bytes() == before


def test_matrix_recorder_new_vintage(tmp_path: Path, monkeypatch, capsys) -> None:
    """NEW_VINTAGE: sha ≠ pin is recorded without tripping the pin."""
    root = stage_repo(tmp_path, runlog_text=OLD_ENTRY + "\n")
    facts = vl.VintageFacts(
        sha256=NEW_SHA,
        byte_size=1674800,
        last_saved="2026-10-01 12:00:00",
        last_saved_by="Laurence Black",
        created="2000-07-15",
        last_row="2026.10",
        k=334.1,
        notes_row="Oct price is Oct 1st close / Oct CPI estimated",
    )
    monkeypatch.setattr(vl, "read_vintage_facts", lambda r: facts)
    monkeypatch.setattr(vl, "capture_suite_result", lambda r: "99/101 pass, 2 FAILED")
    monkeypatch.setattr(vl, "ledger_date", lambda: date(2026, 10, 5))

    rc = vl.record_vintage(root)
    out = capsys.readouterr().out

    assert rc == 0
    text = (root / "data" / "RUNLOG.md").read_text(encoding="utf-8")
    expected = (
        OLD_ENTRY
        + "\n"
        + (
            "## 2026-10-05 — pull from shillerdata.com CDN\n"
            f"- sha256: {NEW_SHA} (1,674,800 bytes) — changed vs §1.1 pin; "
            f"changed vs last entry\n"
            "- last saved: 2026-10-01 12:00:00 by Laurence Black; created 2000-07-15\n"
            "- last row: 2026.10; K (last CPI): 334.1\n"
            "- notes row: Oct price is Oct 1st close / Oct CPI estimated\n"
            "- suite: 99/101 pass, 2 FAILED — as run at record time\n"
            f"- delta: sha256 {OLD_SHA} → {NEW_SHA}; K 332.1 → 334.1; "
            f"last row 2026.08 → 2026.10; "
            f"cell-by-cell diff: PENDING (human step)\n"
        )
    )
    assert text == expected
    # The remaining human re-pull steps are named.
    assert "Remaining human steps" in out
    assert "shiller_io.VINTAGE_SHA256" in out
    assert "DATA.md" in out
    assert "scripts/pipeline.py" in out


def test_recorder_usage_errors(tmp_path: Path) -> None:
    usage = subprocess.run(
        [sys.executable, str(RECORDER_CLI), "a", "b"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert usage.returncode == 2
    missing = stage_repo(tmp_path)
    (missing / "data" / "ie_data.xls").unlink()  # facts-extraction failure
    result = run_recorder(missing)
    assert result.returncode == 1
    assert "re-pull" in result.stderr
