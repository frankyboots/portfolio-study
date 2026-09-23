#!/usr/bin/env python3
"""Edition gate 4 -- accessibility floor (structural seed, pre-1.6).

Concrete seed rules for this story (the accessibility machinery lands
with story 1.6; this gate is an honest structural pass that fails on
seed violations):

- ``config/matplotlibrc`` must exist (the locked style source the
  accessibility floor will verify against).
- Any committed ``*.png`` / ``*.svg`` under ``artifacts/``, ``web/``, or
  ``manual/`` is a seed violation: no export may exist pre-1.6.

"Committed" is the committed set when the root has a ``.git`` tree
(``git ls-files``); without one (staged tmp roots) the working tree is
scanned, since everything on disk is what would be committed.

Mirrors ``scripts/check_import_walls.py``: ``main(argv)``, zero args ->
repo root, OK/FAIL one-liners naming offenders, exit 0 pass / 1
violation / 2 usage error.

Usable standalone:
    uv run python scripts/check_accessibility_floor.py [root]
``<root>`` defaults to the repository root.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SCAN_DIRS = ("artifacts", "web", "manual")
EXPORT_SUFFIXES = (".png", ".svg")


def export_files(root: Path) -> list[str] | None:
    """Committed (or, without .git, on-disk) PNG/SVG exports under the scan dirs.

    Returns ``None`` when the committed set could not be listed (git failure);
    the FAIL line naming the git error is printed here, and ``main`` exits 1.
    """
    names: list[str]
    if (root / ".git").exists():
        proc = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--", *SCAN_DIRS],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            print(
                f"FAIL: accessibility floor: cannot list committed artifacts: {proc.stderr.strip()}",
                file=sys.stderr,
            )
            return None
        names = [line for line in proc.stdout.splitlines() if line]
    else:
        names = []
        for sub in SCAN_DIRS:
            base = root / sub
            if not base.is_dir():
                continue
            names.extend(
                p.relative_to(root).as_posix() for p in base.rglob("*") if p.is_file()
            )
    return sorted(n for n in names if n.endswith(EXPORT_SUFFIXES))


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

    violations: list[str] = []
    rc_file = root / "config" / "matplotlibrc"
    if not rc_file.is_file():
        violations.append(
            f"missing {rc_file.relative_to(root).as_posix()} (locked style source)"
        )
    exports = export_files(root)
    if exports is None:
        return 1
    for name in exports:
        violations.append(f"committed export {name} (no export may exist pre-1.6)")

    if violations:
        for v in violations:
            print(v, file=sys.stderr)
        print(
            "FAIL: accessibility floor: seed violation(s) "
            "(matplotlibrc must exist; no committed exports under artifacts/, web/, manual/)",
            file=sys.stderr,
        )
        return 1
    print(
        "OK: accessibility floor: config/matplotlibrc present; no committed exports "
        "under artifacts/, web/, manual/ (structural seed, pre-1.6)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
