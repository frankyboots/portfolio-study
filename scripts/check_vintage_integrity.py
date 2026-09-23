#!/usr/bin/env python3
"""Standalone CLI for the vintage-integrity gate (story 1.4).

Runs ``analysis.vintage_ledger.check_vintage_integrity(root)``: the build
fails when committed artifact sidecars carry stamps from more than one
Vintage (or from no Vintage at all), when the on-disk
``data/ie_data.xls`` drifts from the pinned sha256, or when the latest
ledger entry does not cover the on-disk vintage -- unless an explicit,
logged override stanza allows the mix. On a pass, any matched override
stanza is announced.

This is the same verdict the pipeline's ``vintage-integrity`` stage runs
(after the artifact stages, so a legitimate full rebuild regenerates all
stamps before judgment); it mirrors ``scripts/check_import_walls.py`` in
shape: ``argv [root]``, OK/FAIL, exit 0/1/2.

Usable standalone:
    uv run python scripts/check_vintage_integrity.py [root]
``<root>`` defaults to the repository root; any root is judged under
``<root>/data/`` and ``<root>/artifacts/``.
Exit codes: 0 pass, 1 any violation (each named), 2 usage error.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) > 1:
        print(f"usage: {Path(sys.argv[0]).name} [root]", file=sys.stderr)
        return 2
    if argv:
        root = Path(argv[0]).resolve()
    else:
        # Default root: the repository (parent of this script's directory).
        root = REPO_ROOT
    if not root.is_dir():
        print(f"error: no such directory: {root}", file=sys.stderr)
        return 2
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from analysis import vintage_ledger

    ok, lines = vintage_ledger.check_vintage_integrity(root)
    for line in lines:
        print(line, file=sys.stderr if not ok else sys.stdout)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
