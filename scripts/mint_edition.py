#!/usr/bin/env python3
"""Mint a committed edition from the built ``web/dist/`` (story 1.7 / AD-5).

    uv run python scripts/mint_edition.py {id}

``{id}`` must match the edition grammar ``^\\d{4}(-\\d+)?$`` (the year
is the mint date, not the data-vintage year; ``{yyyy}-{n}`` marks a
correction in the same year). A built ``web/dist/`` is required. A
``web/editions/{id}/`` that already exists is refused: editions are
frozen once minted, and the CI no-overwrite guard
(``scripts/check_editions.py``) enforces the same rule against the
base ref. The copy excludes a top-level ``editions/`` directory out of
``dist/`` so an edition tree can never contain itself.

Minting does not commit; committing the new edition directory is a
human step (repo commit conventions). Not executed by this story.
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

EDITION_GRAMMAR_RE = re.compile(r"\A\d{4}(-\d+)?\Z")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(f"usage: {Path(sys.argv[0]).name} {{id}}", file=sys.stderr)
        return 2
    edition_id = argv[0]
    if not EDITION_GRAMMAR_RE.match(edition_id):
        print(
            f"refusing: edition id {edition_id!r} is not grammar-conforming "
            r"(expected ^\d{4}(-\d+)?$; the year is the mint date)",
            file=sys.stderr,
        )
        return 1

    dist = REPO_ROOT / "web" / "dist"
    if not dist.is_dir() or not any(dist.iterdir()):
        print(
            f"refusing: no built {dist.as_posix()} (run `cd web && npm run build` "
            "first; minting an unbuilt or empty tree is a no-edition)",
            file=sys.stderr,
        )
        return 1

    target = REPO_ROOT / "web" / "editions" / edition_id
    if target.exists():
        print(
            f"refusing: web/editions/{edition_id} already exists "
            "(editions are frozen once minted; corrections ship as new "
            "edition ids)",
            file=sys.stderr,
        )
        return 1

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(dist, target)
    # Edition recursion guard: an edition tree must never contain itself,
    # even if a future dist layout carries an editions/ directory.
    shutil.rmtree(target / "editions", ignore_errors=True)
    count = sum(1 for p in target.rglob("*") if p.is_file())
    print(
        f"OK: minted web/editions/{edition_id} from web/dist ({count} file(s)); "
        "commit the new directory per the repo commit conventions"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
