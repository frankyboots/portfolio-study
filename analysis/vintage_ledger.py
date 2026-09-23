"""Vintage governance: the RUNLOG ledger owner and the vintage-integrity gate.

Story 1.4: one module owns both halves of the vintage governance.

Ledger
------
``record_vintage`` (CLI: ``scripts/record_vintage.py``) and
``ensure_ledger_covers_vintage`` (the pipeline's ``vintage-integrity``
fallback) read the vintage facts from the file on disk -- sha256 + byte
size, OLE last-saved stamp/author, last row, K = last CPI, notes row --
with the pin bypassed, so a re-pulled file that never matches the pin
yet is readable (the recorder never raises ``VintageError`` on a sha
mismatch). An entry is appended only when the latest ledger entry does
not cover the on-disk vintage (*covers* = the latest entry's
``sha256:`` equals the file on disk); the two paths share one renderer.
The suite subprocess runs only when an append happens -- steady runs
stay cheap.

Gate
----
``check_vintage_integrity(root)`` implements the full verdict matrix:
``MIXED-STAMPS`` (a sidecar stamp outside ``{pin} ∪ logged overrides``),
``UNSTAMPED`` (a sidecar without a valid ``vintage.sha256``),
``DISK-DRIFT`` (on-disk sha256 differs from the pin, or the file is
missing), and ``LATEST-STALE`` (the latest ledger entry does not cover
the on-disk vintage). On a pass, any matched override stanza is
announced; on any violation the caller exits non-zero.

This module lives at the analysis/ top level on purpose: the
import-wall scan covers only the four layer packages, and the ledger
must read both the series layer (sole xlrd owner) and ``data/``
directly.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import olefile

from analysis.series import shiller_io

#: Workbook-relative path of the vintage ledger.
RUNLOG_RELPATH: tuple[str, ...] = ("data", "RUNLOG.md")

#: The artifact tree the gate scans for sidecar stamps.
ARTIFACTS_DIRNAME: str = "artifacts"
SIDECAR_SUFFIX: str = "meta.json"

#: Header written when a machine path has to create the ledger file.
_MINIMAL_LEDGER: str = "# RUNLOG — ie_data.xls vintage ledger\n\n---\n\n"

_ENTRY_HEADING_RE: re.Pattern[str] = re.compile(r"^## (\d{4}-\d{2}-\d{2}) — (.+)$")
_SHA64_RE: re.Pattern[str] = re.compile(r"[0-9a-fA-F]{64}")
_LAST_ROW_RE: re.Pattern[str] = re.compile(r"\b(\d{4}\.\d{1,2})\b")
_K_RE: re.Pattern[str] = re.compile(r"K \(last CPI\):\s*\**\s*([0-9][0-9eE.+-]*)")
_SUITE_SUMMARY_RE: re.Pattern[str] = re.compile(r"^(\d+)/(\d+) passed, (\d+) failed$")
#: Strict override stanza: one bullet, shas space-separated, full 64-hex each.
_OVERRIDE_RE: re.Pattern[str] = re.compile(
    r"^- override: allow-vintages ([0-9a-f]{64}(?: [0-9a-f]{64})*)"
    r" — reason: (.+?) — logged by: (.+?) — date: (\d{4}-\d{2}-\d{2})\s*$"
)


class LedgerError(Exception):
    """Raised when ledger facts cannot be read or the suite gives no summary."""


@dataclass(frozen=True)
class VintageFacts:
    """The ledger facts of one on-disk file, read from disk (never hand-typed)."""

    sha256: str
    byte_size: int
    last_saved: str  # OLE last-saved timestamp, "YYYY-MM-DD HH:MM:SS"
    last_saved_by: str
    created: str  # OLE created date, "YYYY-MM-DD"
    last_row: str  # "YYYY.MM"
    k: float  # K = last CPI (DATA.md §4)
    notes_row: str  # last sheet row, non-blank segments joined with " / "


@dataclass(frozen=True)
class LedgerEntry:
    """One parsed ``## YYYY-MM-DD`` entry; unparsed fields are ``None``."""

    date: str
    sha256: str | None
    k: str | None  # as recorded (verbatim string)
    last_row: str | None  # as recorded (verbatim string)


@dataclass(frozen=True)
class OverrideStanza:
    """A parsed human override amendment appended to an entry."""

    raw: str
    shas: tuple[str, ...]
    reason: str
    logged_by: str
    date: str


def ledger_date() -> date:
    """The entry date for a machine append: today in UTC (the pinned TZ)."""
    return datetime.now(UTC).date()


def _sha256_bytes(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest(), path.stat().st_size


def _text(value: object) -> str:
    """OLE metadata values may be bytes; normalize to str."""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


# ---------------------------------------------------------------- ledger facts


def read_vintage_facts(root: Path) -> VintageFacts:
    """Read all ledger facts from the file on disk; the pin is bypassed.

    This is the pin-optional facts path (``shiller_io.load_vintage`` with
    ``pin=None``), used only by the recorder and the pipeline fallback so
    a re-pulled file that never matches the pin yet stays readable.
    """
    path = root.joinpath(*shiller_io.XLS_RELPATH)
    if not path.is_file():
        raise LedgerError(
            f"missing dataset {path.relative_to(root).as_posix()}; re-pull per "
            f"data/RUNLOG.md (shillerdata.com CDN; do not use the stale Yale mirror)"
        )
    sha, size = _sha256_bytes(path)
    try:
        meta = olefile.OleFileIO(str(path)).get_metadata()
        ts = meta.last_saved_time
        created = meta.create_time
        if ts is None or created is None:
            raise LedgerError(
                f"OLE metadata lacks the last-saved/create time in "
                f"{path.relative_to(root).as_posix()}"
            )
        vintage = shiller_io.load_vintage(root, pin=None)
    except LedgerError:
        raise
    except Exception as exc:  # any extraction crash becomes a LedgerError
        raise LedgerError(
            f"facts extraction failed for {path.relative_to(root).as_posix()}: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    return VintageFacts(
        sha256=sha,
        byte_size=size,
        last_saved=(
            f"{ts.year:04d}-{ts.month:02d}-{ts.day:02d} "
            f"{ts.hour:02d}:{ts.minute:02d}:{ts.second:02d}"
        ),
        last_saved_by=_text(meta.last_saved_by),
        created=f"{created.year:04d}-{created.month:02d}-{created.day:02d}",
        last_row=f"{vintage.last_row[0]}.{vintage.last_row[1]:02d}",
        k=vintage.k,
        notes_row=vintage.notes_row,
    )


# ---------------------------------------------------------------- suite capture


def parse_suite_summary(stdout: str) -> str:
    """Parse the suite's ``N/M passed, F failed`` line into the ledger form.

    ``101/101 passed, 0 failed`` -> ``"101/101 pass"``;
    ``99/101 passed, 2 failed`` -> ``"99/101 pass, 2 FAILED"``.
    Raises :class:`LedgerError` when no summary line is present.
    """
    for line in reversed(stdout.splitlines()):
        m = _SUITE_SUMMARY_RE.match(line.strip())
        if m is None:
            continue
        passed, total, failed = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if failed == 0:
            return f"{passed}/{total} pass"
        return f"{passed}/{total} pass, {failed} FAILED"
    raise LedgerError("no 'N/M passed, F failed' summary line in the suite output")


def capture_suite_result(root: Path) -> str:
    """Run ``analysis/validate_data_md.py`` as a subprocess; return the line.

    The count is never hardcoded: it is parsed from the summary line the
    suite prints at record time.
    """
    script = root.joinpath("analysis", "validate_data_md.py")
    if not script.is_file():
        raise LedgerError(f"missing validation suite {script}")
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        check=False,  # intentional: a FAILED suite still yields a recordable line
    )
    try:
        return parse_suite_summary(result.stdout)
    except LedgerError:
        tail = (result.stderr.strip().splitlines() or ["<no stderr>"])[-1]
        raise LedgerError(
            f"validation suite produced no summary line (exit {result.returncode}): {tail}"
        ) from None


# ---------------------------------------------------------------- ledger parse


def parse_ledger(text: str) -> tuple[list[LedgerEntry], list[OverrideStanza]]:
    """Parse ``data/RUNLOG.md``: ``##`` entries plus strict override stanzas.

    Entry fields are read verbatim (tolerating the backticks and ``**``
    emphasis the seed entry carries); a malformed stanza is simply not
    a stanza -- the gate trusts nothing it cannot parse strictly.
    """
    entries: list[LedgerEntry] = []
    stanzas: list[OverrideStanza] = []
    current: dict[str, str | None] | None = None
    for line in text.splitlines():
        heading = _ENTRY_HEADING_RE.match(line)
        if heading:
            if current is not None:
                entries.append(
                    LedgerEntry(
                        date=current["date"] or "",
                        sha256=current["sha256"],
                        k=current["k"],
                        last_row=current["last_row"],
                    )
                )
            current = {
                "date": heading.group(1),
                "sha256": None,
                "k": None,
                "last_row": None,
            }
            continue
        if current is None:
            continue
        override = _OVERRIDE_RE.match(line)
        if override:
            stanzas.append(
                OverrideStanza(
                    raw=line,
                    shas=tuple(override.group(1).split(" ")),
                    reason=override.group(2),
                    logged_by=override.group(3),
                    date=override.group(4),
                )
            )
            continue
        if line.startswith("- sha256:"):
            sha_match = _SHA64_RE.search(line)
            if sha_match and current["sha256"] is None:
                current["sha256"] = sha_match.group(0).lower()
        if line.startswith("- last row:"):
            row_match = _LAST_ROW_RE.search(line)
            if row_match and current["last_row"] is None:
                current["last_row"] = row_match.group(1)
            k_match = _K_RE.search(line)
            if k_match and current["k"] is None:
                current["k"] = k_match.group(1)
    if current is not None:
        entries.append(
            LedgerEntry(
                date=current["date"] or "",
                sha256=current["sha256"],
                k=current["k"],
                last_row=current["last_row"],
            )
        )
    return entries, stanzas


def _read_ledger(root: Path) -> tuple[list[LedgerEntry], list[OverrideStanza]]:
    path = root.joinpath(*RUNLOG_RELPATH)
    if not path.is_file():
        return [], []
    return parse_ledger(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- entry rendering


def render_entry(
    facts: VintageFacts,
    *,
    pin: str,
    previous: LedgerEntry | None,
    record_date: date,
    suite_line: str,
) -> str:
    """Render the machine entry byte-for-byte in the RUNLOG.md format.

    Delta vs the prior entry: no prior entry -> ``none (first ledger
    entry)``; recorded bytes equal the pin -> ``none (identical bytes to
    the pinned vintage)``; otherwise the machine-verifiable deltas with
    the full cell-by-cell diff marked PENDING (human step).
    """
    pin_cmp = "same as §1.1 pin" if facts.sha256 == pin else "changed vs §1.1 pin"
    if previous is None:
        tail = "no prior ledger entry"
        delta = "none (first ledger entry)"
    else:
        last_cmp = (
            "same as last entry"
            if previous.sha256 == facts.sha256
            else "changed vs last entry"
        )
        tail = last_cmp
        if facts.sha256 == pin:
            delta = "none (identical bytes to the pinned vintage)"
        else:
            delta = (
                f"sha256 {previous.sha256 or 'unknown'} → {facts.sha256}; "
                f"K {previous.k or 'unknown'} → {facts.k!r}; "
                f"last row {previous.last_row or 'unknown'} → {facts.last_row}; "
                f"cell-by-cell diff: PENDING (human step)"
            )
    lines = [
        f"## {record_date.isoformat()} — pull from shillerdata.com CDN",
        f"- sha256: {facts.sha256} ({facts.byte_size:,} bytes) — {pin_cmp}; {tail}",
        (
            f"- last saved: {facts.last_saved} by {facts.last_saved_by}; "
            f"created {facts.created}"
        ),
        f"- last row: {facts.last_row}; K (last CPI): {facts.k!r}",
        f"- notes row: {facts.notes_row}",
        f"- suite: {suite_line} — as run at record time",
        f"- delta: {delta}",
    ]
    return "\n".join(lines) + "\n"


def append_entry(root: Path, entry_text: str) -> None:
    """Append one rendered entry to ``data/RUNLOG.md`` (create it if absent)."""
    path = root.joinpath(*RUNLOG_RELPATH)
    if path.is_file():
        text = path.read_text(encoding="utf-8")
        if not text.endswith("\n"):
            text += "\n"
        path.write_text(text + entry_text, encoding="utf-8")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_MINIMAL_LEDGER + entry_text, encoding="utf-8")


# ---------------------------------------------------------------- append paths


def ensure_ledger_covers_vintage(root: Path) -> bool:
    """LATEST-STALE fallback: append the missing entry, post-hoc.

    Runs in the pipeline's ``vintage-integrity`` stage before the gate
    verdict. Appends (and captures the suite only then) when the latest
    ledger entry does not cover the on-disk vintage. Returns ``True``
    when an entry was appended.
    """
    entries, _ = _read_ledger(root)
    xls = root.joinpath(*shiller_io.XLS_RELPATH)
    if not xls.is_file():
        return False  # unreadable facts; the gate's DISK-DRIFT verdict names this
    disk_sha, _ = _sha256_bytes(xls)
    if entries and entries[-1].sha256 == disk_sha:
        return False
    facts = read_vintage_facts(root)
    suite_line = capture_suite_result(root)
    entry_text = render_entry(
        facts,
        pin=shiller_io.VINTAGE_SHA256,
        previous=entries[-1] if entries else None,
        record_date=ledger_date(),
        suite_line=suite_line,
    )
    append_entry(root, entry_text)
    return True


def record_vintage(root: Path) -> int:
    """Recorder CLI body: append the entry for a re-pulled vintage.

    Returns 0 when an entry was appended or the latest entry already
    covers the on-disk vintage (no-op), and 1 on facts-extraction or
    suite-run failure. The pin is bypassed (a re-pulled file never
    matches the pin yet) and a failing suite is recorded, not fatal.
    """
    pin = shiller_io.VINTAGE_SHA256
    entries, _ = _read_ledger(root)
    xls = root.joinpath(*shiller_io.XLS_RELPATH)
    if not xls.is_file():
        print(
            f"record-vintage: missing {'/'.join(shiller_io.XLS_RELPATH)}; re-pull it per "
            f"data/RUNLOG.md first",
            file=sys.stderr,
        )
        return 1
    disk_sha, _ = _sha256_bytes(xls)
    if entries and entries[-1].sha256 == disk_sha:
        print(
            f"no-op: the latest ledger entry already covers the on-disk vintage "
            f"(sha256 {disk_sha}); RUNLOG.md unchanged"
        )
        return 0
    try:
        facts = read_vintage_facts(root)
        suite_line = capture_suite_result(root)
    except LedgerError as exc:
        print(f"record-vintage: {exc}", file=sys.stderr)
        return 1
    entry_text = render_entry(
        facts,
        pin=pin,
        previous=entries[-1] if entries else None,
        record_date=ledger_date(),
        suite_line=suite_line,
    )
    append_entry(root, entry_text)
    print(entry_text, end="")
    print(
        "Remaining human steps (the recorder never edits the pin, DATA.md, or diffs):"
    )
    for step in (
        f"1. update the §1.1 pin (data/DATA.md + shiller_io.VINTAGE_SHA256) to {facts.sha256}",
        "2. re-verify DATA.md's vintage-sensitive numbers (K, last-row stats, tail estimates)",
        "3. complete the cell-by-cell diff that the entry's delta line marks PENDING",
        (
            "4. rebuild: uv run python scripts/pipeline.py "
            "(the vintage-integrity stage re-verifies the binding)"
        ),
    ):
        print(step)
    return 0


# ---------------------------------------------------------------- the gate


def check_vintage_integrity(root: Path) -> tuple[bool, list[str]]:
    """The vintage-integrity gate: one Vintage bound, or the build fails.

    Fails (returning ``(False, lines)``) on any of: ``DISK-DRIFT`` (the
    on-disk sha256 differs from the pin, or the file is missing),
    ``UNSTAMPED`` (a sidecar without a valid ``vintage.sha256``),
    ``MIXED-STAMPS`` (a sidecar stamp outside ``{pin} ∪ logged overrides``),
    and ``LATEST-STALE`` (the latest ledger entry does not cover the
    on-disk vintage). Returns ``(True, lines)`` otherwise, with any
    matched override stanza announced.
    """
    pin = shiller_io.VINTAGE_SHA256
    entries, stanzas = _read_ledger(root)
    violations: list[str] = []

    xls_rel = "/".join(shiller_io.XLS_RELPATH)
    disk_sha: str | None
    if not root.joinpath(*shiller_io.XLS_RELPATH).is_file():
        disk_sha = None
        violations.append(
            f"DISK-DRIFT: {xls_rel} is missing; re-pull per data/RUNLOG.md "
            f"(cannot verify the pin {pin})"
        )
    else:
        disk_sha, _ = _sha256_bytes(root.joinpath(*shiller_io.XLS_RELPATH))
        if disk_sha != pin:
            violations.append(
                f"DISK-DRIFT: sha256({xls_rel}) is {disk_sha} but the pinned "
                f"vintage is {pin}; restore the pinned file or complete the "
                f"re-pull procedure"
            )

    stamps: list[tuple[str, str]] = []  # (sidecar relpath, vintage sha256)
    artifacts_dir = root / ARTIFACTS_DIRNAME
    if artifacts_dir.is_dir():
        for sidecar in sorted(artifacts_dir.rglob(f"*.{SIDECAR_SUFFIX}")):
            rel = sidecar.relative_to(root).as_posix()
            try:
                obj = json.loads(sidecar.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                violations.append(f"UNSTAMPED: {rel} is unreadable ({exc})")
                continue
            vintage = obj.get("vintage") if isinstance(obj, dict) else None
            sha = vintage.get("sha256") if isinstance(vintage, dict) else None
            if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
                violations.append(
                    f"UNSTAMPED: {rel} carries no sidecar vintage stamp "
                    f"(vintage.sha256)"
                )
            else:
                stamps.append((rel, sha))

    allowed = {pin, *(sha for stanza in stanzas for sha in stanza.shas)}
    by_sha: dict[str, list[str]] = {}
    for rel, sha in stamps:
        if sha not in allowed:
            by_sha.setdefault(sha, []).append(rel)
    if by_sha:
        groups = "; ".join(
            f"sha256 {sha} — {', '.join(rels)}" for sha, rels in sorted(by_sha.items())
        )
        violations.append(
            "MIXED-STAMPS: sidecar stamps fall outside {pin} ∪ logged overrides; "
            f"the pin is {pin}: {groups}"
        )

    reference_sha = disk_sha if disk_sha is not None else pin
    if disk_sha is not None:
        reference_text = f"on-disk vintage (sha256 {disk_sha})"
    else:
        reference_text = f"on-disk vintage (file missing; reference is the pin {pin})"
    if not entries:
        violations.append(
            f"LATEST-STALE: no ledger entries in {'/'.join(RUNLOG_RELPATH)}; the "
            f"{reference_text} is not on record — run scripts/record_vintage.py"
        )
    elif entries[-1].sha256 != reference_sha:
        violations.append(
            f"LATEST-STALE: latest ledger entry (sha256 "
            f"{entries[-1].sha256 or 'unparsed'}) does not cover the "
            f"{reference_text}; run scripts/record_vintage.py "
            f"or let the pipeline's vintage-integrity stage append"
        )

    if violations:
        return False, [
            f"FAIL: vintage integrity ({len(violations)} violation group(s))",
            *violations,
        ]

    stamp_shas = {sha for _, sha in stamps}
    matched = [stanza for stanza in stanzas if set(stanza.shas) & stamp_shas]
    lines = [
        (
            f"OK: vintage integrity — disk sha256 matches pin {pin}, "
            f"{len(stamps)} sidecar stamp(s) within the allowed set, latest ledger "
            f"entry covers the on-disk vintage"
        )
    ]
    lines.extend(f"OVERRIDE STANZA IN FORCE: {stanza.raw}" for stanza in matched)
    return True, lines
