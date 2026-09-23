#!/usr/bin/env python3
"""Edition gate 6 -- cross-doc consistency vs ``data/DATA.md``
(structural seed).

Scan surface: committed markdown under ``docs/``, ``web/``, ``manual/``
(whichever exist; none do today, so the gate is a structural pass).
"Committed" is the committed set when the root has a ``.git`` tree
(``git ls-files``); without one (staged tmp roots) the working tree is
scanned, since everything on disk is what would be committed.

On any line mentioning the dataset (``ie_data`` or ``Shiller``,
case-insensitive), candidate vintage facts are extracted and compared
against ``data/DATA.md`` section 1.1:

- 64-hex strings must equal the 1.1 pin;
- a ``K`` float (``K = <float>`` / ``K: <float>`` /
  ``K (last CPI) = <float>``) must equal 1.1's K;
- a ``YYYY.MM`` last-row claim (a ``YYYY.MM`` on a line saying
  "last row") must equal 1.1's last row.

Any mismatch exits 1 naming ``file:line``. The DATA.md reader depends
on no more than the 1.1 section's sha256 bullet line, K cell, and
last-row cell.

Mirrors ``scripts/check_import_walls.py``: ``main(argv)``, zero args ->
repo root, OK/FAIL one-liners naming offenders, exit 0 pass / 1
violation / 2 usage error.

Usable standalone:
    uv run python scripts/check_crossdoc_consistency.py [root]
``<root>`` defaults to the repository root.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SCAN_DIRS = ("docs", "web", "manual")
HEX64_RE = re.compile(r"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])")
K_RE = re.compile(r"\bK\s*(?:\(last CPI\))?\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)")
LAST_ROW_RE = re.compile(r"\b(1[89][0-9]{2}|20[0-9]{2})\.([0-9]{2})\b")
MARKERS_RE = re.compile(r"ie_data|shiller", re.IGNORECASE)

PIN_RE = re.compile(r"sha256: ([0-9a-f]{64})")
K_PIN_RE = re.compile(r"K \(last CPI\) \*\*([0-9]+(?:\.[0-9]+)?)\*\*")
LAST_ROW_PIN_RE = re.compile(r"last row \*\*(\d{4}\.\d{2})\*\*")


def scan_files(root: Path) -> list[Path] | None:
    """Committed (or, without .git, on-disk) markdown under the scan dirs.

    Returns ``None`` when the committed set could not be listed (git failure);
    the FAIL line naming the git error is printed here, and ``main`` exits 1.
    """
    if (root / ".git").exists():
        proc = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--", *SCAN_DIRS],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            print(
                f"FAIL: cross-doc consistency: cannot list committed markdown: {proc.stderr.strip()}",
                file=sys.stderr,
            )
            return None
        names = [line for line in proc.stdout.splitlines() if line]
    else:
        names = [
            p.relative_to(root).as_posix()
            for sub in SCAN_DIRS
            if (root / sub).is_dir()
            for p in (root / sub).rglob("*.md")
            if p.is_file()
        ]
    return sorted(root / n for n in names if n.endswith(".md"))


def parse_pin(root: Path) -> tuple[str, float, str]:
    """(sha256, K, last row) from ``data/DATA.md`` section 1.1.

    Raises ``ValueError`` naming the missing fact when the section
    cannot be read (a DATA.md format break the gate must not pass).
    """
    data_md = root / "data" / "DATA.md"
    if not data_md.is_file():
        raise ValueError(f"missing {data_md.as_posix()} -- nothing to compare against")
    text = data_md.read_text(encoding="utf-8")
    # The 1.1 section header at any level 2-3 (today: '### 1.1 ...'), ending
    # at the next level 2-3 header -- never bleeding into a sibling section.
    start_match = re.search(r"(?m)^#{2,3} 1\.1\b", text)
    if not start_match:
        raise ValueError("data/DATA.md has no level 2-3 '1.1' section header")
    next_header = re.search(r"(?m)^#{2,3} ", text[start_match.end() :])
    end = start_match.end() + next_header.start() if next_header else len(text)
    section = text[start_match.start() : end]
    pin = PIN_RE.search(section)
    k = K_PIN_RE.search(section)
    last_row = LAST_ROW_PIN_RE.search(section)
    if not pin:
        raise ValueError("data/DATA.md section 1.1 has no 'sha256: <64-hex>' pin line")
    if not k:
        raise ValueError("data/DATA.md section 1.1 has no K (last CPI) value")
    if not last_row:
        raise ValueError("data/DATA.md section 1.1 has no last-row value")
    return pin.group(1), float(k.group(1)), last_row.group(1)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) > 1:
        print(f"usage: {Path(sys.argv[0]).name} [root]", file=sys.stderr)
        return 2
    if argv:
        root = Path(argv[0]).resolve()
    else:
        root = REPO_ROOT
    if not root.is_dir():
        print(f"error: no such directory: {root}", file=sys.stderr)
        return 2

    try:
        pin, pin_k, pin_last_row = parse_pin(root)
    except ValueError as exc:
        print(f"FAIL: cross-doc consistency: {exc}", file=sys.stderr)
        return 1

    files = scan_files(root)
    if files is None:
        return 1
    if not files:
        print(
            "OK: cross-doc consistency: no committed markdown under docs/, web/, manual/ "
            "-- structural pass"
        )
        return 0

    checked_lines = 0
    violations: list[str] = []
    for path in files:
        rel = path.relative_to(root).as_posix()
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not MARKERS_RE.search(line):
                continue
            checked_lines += 1
            for hex_candidate in HEX64_RE.findall(line):
                if hex_candidate != pin:
                    violations.append(
                        f"{rel}:{lineno}: vintage sha256 {hex_candidate[:12]}... != DATA.md 1.1 pin {pin[:12]}..."
                    )
            for k_candidate in K_RE.findall(line):
                if abs(float(k_candidate) - pin_k) > 1e-9:
                    violations.append(
                        f"{rel}:{lineno}: K {k_candidate} != DATA.md 1.1 K {pin_k}"
                    )
            if re.search(r"last row", line, re.IGNORECASE):
                for years, months in LAST_ROW_RE.findall(line):
                    month = int(months)
                    if 1 <= month <= 12 and f"{years}.{months}" != pin_last_row:
                        violations.append(
                            f"{rel}:{lineno}: last row {years}.{months} != DATA.md 1.1 last row {pin_last_row}"
                        )
    if violations:
        for v in violations:
            print(v, file=sys.stderr)
        print(
            "FAIL: cross-doc consistency: candidate vintage fact(s) disagree with data/DATA.md 1.1",
            file=sys.stderr,
        )
        return 1
    print(
        f"OK: cross-doc consistency: {len(files)} markdown file(s) under docs/, web/, manual/, "
        f"{checked_lines} dataset line(s) checked against data/DATA.md 1.1"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
