#!/usr/bin/env python3
"""Standalone vintage-ledger recorder CLI (story 1.4).

Records a re-pull in ``data/RUNLOG.md``: reads the vintage facts from
the file on disk (sha256 + bytes, OLE last-saved stamp/author, last
row, K = last CPI, notes row) with the pin bypassed -- a re-pulled file
never matches the pin yet, so the recorder never raises ``VintageError``
on a sha mismatch -- runs ``analysis/validate_data_md.py`` as a
subprocess, and appends the machine entry with the machine-computed
delta vs the prior entry. It then prints the remaining human re-pull
steps (update the pin, re-verify DATA.md, complete the PENDING
cell-by-cell diff, rebuild).

Append cadence: an entry is written only when the latest ledger entry
does not cover the on-disk vintage (*covers* = the latest entry's
``sha256:`` equals the file on disk); a steady tree is a no-op. The
suite subprocess runs only on the append path. A failing suite is
recorded (``<n>/<m> pass, <f> FAILED``), not fatal.

Usable standalone:
    uv run python scripts/record_vintage.py [root]
``<root>`` defaults to the repository root.
Exit codes: 0 appended / 0 no-op-already-covered / 2 usage / 1
facts-extraction or suite-run failure.
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

    return vintage_ledger.record_vintage(root)


if __name__ == "__main__":
    sys.exit(main())
