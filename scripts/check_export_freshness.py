#!/usr/bin/env python3
"""Edition gate 7 -- export freshness (structural seed, pre-1.6).

Same export glob as gate 4: committed ``*.png`` / ``*.svg`` under
``artifacts/``, ``web/``, or ``manual/`` ("committed" = ``git
ls-files`` when the root has a ``.git`` tree, else the working tree,
since everything on disk is what would be committed). Since no
generator exists pre-1.6, any committed export is a violation --
there is nothing to verify freshness against; zero exports is a
structural pass. Once story 1.6 lands, this gate regrows to
regenerate-and-diff.

Mirrors ``scripts/check_import_walls.py``: ``main(argv)``, zero args ->
repo root, OK/FAIL one-liners naming offenders, exit 0 pass / 1
violation / 2 usage error.

Usable standalone:
    uv run python scripts/check_export_freshness.py [root]
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
                f"FAIL: export freshness: cannot list committed exports: {proc.stderr.strip()}",
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

    exports = export_files(root)
    if exports is None:
        return 1
    if exports:
        for name in exports:
            print(
                f"committed export {name} (no generator exists pre-1.6; nothing to verify against)",
                file=sys.stderr,
            )
        print(
            "FAIL: export freshness: committed export(s) under artifacts/, web/, manual/ "
            "with no generator to verify freshness against (structural seed, pre-1.6)",
            file=sys.stderr,
        )
        return 1
    print(
        "OK: export freshness: no committed exports under artifacts/, web/, manual/ "
        "(structural pass pre-1.6; regrows to regenerate-and-diff)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
